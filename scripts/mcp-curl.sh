#!/usr/bin/env bash
#
# Drive an x402guard MCP endpoint with curl + jq — hand-held demo.
#
# Same purpose as scripts/demo.py: prove the MCP endpoint is healthy
# without any MCP client, but using only bash / curl / jq.
#
# Usage:
#
#   # 1. Read-only (default) — tools/list + balance + history
#   ./scripts/mcp-curl.sh https://x402guard.acedata.cloud/mcp/<TOKEN>
#
#   # 2. Spend mode — actually moves USDC on devnet.
#   ./scripts/mcp-curl.sh https://x402guard.acedata.cloud/mcp/<TOKEN> \
#       --spend --recipient <YOUR-PHANTOM-ADDRESS>
#
#   # 3. Pay-for-API mode — full x402 dance (mainnet-only as of devnet deploy)
#   ./scripts/mcp-curl.sh https://x402guard.acedata.cloud/mcp/<TOKEN> --pay-for-api
#
# Optional env (apply only to --spend / --pay-for-api):
#   AMOUNT         spend amount in USDC          (default 0.01, --spend only)
#   ENDPOINT_HOST  endpoint host on allowlist    (default api.acedata.cloud)
#   API_URL        upstream API in --pay-for-api (default openai chat completions)
#   API_BODY       JSON body for that API        (default 5-word "hi" prompt)

set -euo pipefail

if [ "${#}" -lt 1 ]; then
    cat >&2 <<USAGE
usage: $0 <MCP-URL> [--spend --recipient <PUBKEY> [--amount X] [--endpoint-host HOST]]
       $0 <MCP-URL> [--pay-for-api [--api-url URL] [--api-body JSON]]

  default mode: read-only (no on-chain tx). Pass --spend to actually spend.

Examples:
  $0 https://x402guard.acedata.cloud/mcp/abc123                                # read-only
  $0 https://x402guard.acedata.cloud/mcp/abc123 --spend --recipient 7v3...     # 0.01 USDC tx
USAGE
    exit 64
fi

URL="$1"
shift

MODE="readonly"
RECIPIENT=""
AMOUNT="${AMOUNT:-0.01}"
ENDPOINT_HOST="${ENDPOINT_HOST:-api.acedata.cloud}"
API_URL="${API_URL:-https://api.acedata.cloud/openai/chat/completions}"
API_BODY="${API_BODY:-{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi in 5 words.\"}],\"max_tokens\":20}}"

while [ "${#}" -gt 0 ]; do
    case "$1" in
        --spend)             MODE="spend"; shift ;;
        --pay-for-api)       MODE="pay";   shift ;;
        --recipient)         RECIPIENT="$2"; shift 2 ;;
        --amount)            AMOUNT="$2"; shift 2 ;;
        --endpoint-host)     ENDPOINT_HOST="$2"; shift 2 ;;
        --api-url)           API_URL="$2"; shift 2 ;;
        --api-body)          API_BODY="$2"; shift 2 ;;
        -h|--help)           sed -n '/^#$/,/^$/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 64 ;;
    esac
done

if [ "$MODE" = "spend" ] && [ -z "$RECIPIENT" ]; then
    echo "❌ --spend requires --recipient <SOLANA-PUBKEY>" >&2
    exit 64
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ this script needs jq. install with: brew install jq" >&2
    exit 127
fi

call() {
    # call <id> <method> <params-json>
    local id="$1" method="$2" params="${3:-null}"
    curl -sS -X POST "$URL" \
        -H 'content-type: application/json' \
        --data "{\"jsonrpc\":\"2.0\",\"id\":${id},\"method\":\"${method}\",\"params\":${params}}"
}

echo "x402guard CLI demo (bash) — driving MCP at $URL"
case "$MODE" in
    readonly) echo "  mode: read-only (no on-chain tx; pass --spend or --pay-for-api to do one)" ;;
    spend)    echo "  mode: --spend  recipient=$RECIPIENT  amount=$AMOUNT USDC  endpoint=$ENDPOINT_HOST" ;;
    pay)      echo "  mode: --pay-for-api  url=$API_URL" ;;
esac

echo
echo "━━━ 1. tools/list ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
call 1 "tools/list" "null" \
    | jq '.result.tools[] | {name, description: ((.description // "")[0:80])}'

echo
echo "━━━ 2. aceguard_balance (before) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
BAL_BEFORE_RAW=$(call 2 "tools/call" '{"name":"aceguard_balance","arguments":{}}')
BAL_BEFORE=$(echo "$BAL_BEFORE_RAW" | jq -r '.result.content[0].text')
echo "$BAL_BEFORE" | jq

PAUSED=$(echo "$BAL_BEFORE" | jq -r '.paused')
BALANCE=$(echo "$BAL_BEFORE" | jq -r '.balance_usdc')

if [ "$MODE" = "spend" ]; then
    if [ "$PAUSED" = "true" ]; then
        echo "❌ vault is paused; resume it in the Dapp first" >&2
        exit 2
    fi
    if awk -v b="$BALANCE" -v a="$AMOUNT" 'BEGIN{exit !(b+0 < a+0)}'; then
        echo "❌ vault balance ($BALANCE USDC) is below --amount ($AMOUNT USDC). Top up via the Dapp." >&2
        exit 2
    fi

    echo
    echo "━━━ 3. aceguard_spend  →  $AMOUNT USDC → $RECIPIENT ━━━━━━━━━━━━━━━"
    SPEND_PARAMS=$(jq -n \
        --arg recipient "$RECIPIENT" \
        --arg endpoint  "$ENDPOINT_HOST" \
        --argjson amt   "$AMOUNT" \
        '{name:"aceguard_spend",arguments:{amount_usdc:$amt,recipient:$recipient,endpoint_host:$endpoint}}')
    SPEND_RESULT=$(call 3 "tools/call" "$SPEND_PARAMS")
    echo "$SPEND_RESULT" | jq -r '.result.content[0].text' | jq
    IS_ERROR=$(echo "$SPEND_RESULT" | jq -r '.result.isError // false')
    if [ "$IS_ERROR" = "true" ]; then
        echo "⚠️  spend isError=true. Likely: recipient ATA missing on devnet, allowlist mismatch, cap exceeded, or paused." >&2
        exit 3
    fi

    echo
    echo "━━━ 4. aceguard_balance (after) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    call 4 "tools/call" '{"name":"aceguard_balance","arguments":{}}' \
        | jq -r '.result.content[0].text' \
        | jq '{balance_usdc, spent_today_usdc, daily_remaining_usdc, paused}'

elif [ "$MODE" = "pay" ]; then
    echo
    echo "━━━ 3. aceguard_pay_for_api  →  POST $API_URL ━━━━━━━━━━━━━━━━━━━━━"
    PAY_PARAMS=$(jq -n --arg url "$API_URL" --argjson body "$API_BODY" \
        '{name:"aceguard_pay_for_api",arguments:{url:$url,method:"POST",json_body:$body}}')
    PAY_RESULT=$(call 3 "tools/call" "$PAY_PARAMS")
    echo "$PAY_RESULT" | jq -r '.result.content[0].text' \
        | jq '. | del(.upstream_response) | . + {_upstream_status: .upstream_status}'
    IS_ERROR=$(echo "$PAY_RESULT" | jq -r '.result.isError // false')
    if [ "$IS_ERROR" = "true" ]; then
        echo "⚠️  pay_for_api isError=true. As of devnet deploy api.acedata.cloud is mainnet-only — see README." >&2
        exit 3
    fi

    echo
    echo "━━━ 4. aceguard_balance (after) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    call 4 "tools/call" '{"name":"aceguard_balance","arguments":{}}' \
        | jq -r '.result.content[0].text' \
        | jq '{balance_usdc, spent_today_usdc, daily_remaining_usdc, paused}'
fi

echo
echo "━━━ 5. aceguard_history (latest 5) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
call 5 "tools/call" '{"name":"aceguard_history","arguments":{"limit":5}}' \
    | jq -r '.result.content[0].text' \
    | jq '.spends // [] | .[] | {block_time, amount_usdc, recipient, endpoint, solscan}'

echo
echo "✅ done."
if [ "$MODE" = "readonly" ]; then
    echo "   (Endpoint is healthy. To do a real spend, re-run with --spend --recipient <your Phantom wallet>.)"
fi
