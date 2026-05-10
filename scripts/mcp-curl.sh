#!/usr/bin/env bash
#
# Drive an x402guard MCP endpoint with curl + jq.
#
# Same purpose as scripts/demo.py — proves the MCP endpoint is healthy
# without any MCP client, but using only bash / curl / jq for users
# who don't have a Python toolchain handy.
#
# Usage:
#
#   ./scripts/mcp-curl.sh https://x402guard.acedata.cloud/mcp/<TOKEN>
#
# Optional env:
#   API_URL    upstream API to pay for       (default: openai chat completions)
#   API_BODY   JSON body for that API        (default: 5-word "hi" prompt)
#
# What it does:
#   1. tools/list            (lists the four aceguard tools)
#   2. aceguard_balance      (reads on-chain USDC + caps)
#   3. aceguard_pay_for_api  (full x402 + on-chain spend round-trip)
#   4. aceguard_balance      (confirms balance ticked down)

set -euo pipefail

if [ "${#}" -lt 1 ]; then
    echo "usage: $0 <MCP-URL>" >&2
    echo "       e.g. $0 https://x402guard.acedata.cloud/mcp/abc123..." >&2
    exit 64
fi

URL="$1"
API_URL="${API_URL:-https://api.acedata.cloud/openai/chat/completions}"
API_BODY="${API_BODY:-{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi in 5 words.\"}],\"max_tokens\":20}}"

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

echo "━━━ 1. tools/list ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
call 1 "tools/list" "null" | jq '.result.tools[] | {name, description: (.description | .[0:80])}'

echo
echo "━━━ 2. aceguard_balance ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
BAL_BEFORE=$(call 2 "tools/call" '{"name":"aceguard_balance","arguments":{}}' \
    | jq -r '.result.content[0].text')
echo "$BAL_BEFORE" | jq

PAUSED=$(echo "$BAL_BEFORE" | jq -r '.paused')
BALANCE=$(echo "$BAL_BEFORE" | jq -r '.balance_usdc')
if [ "$PAUSED" = "true" ]; then
    echo "❌ vault is paused; resume it in the Dapp first" >&2
    exit 2
fi
if [ "$(echo "$BALANCE <= 0" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
    echo "❌ vault balance is 0 USDC; top up via the Dapp first" >&2
    exit 2
fi

echo
echo "━━━ 3. aceguard_pay_for_api  →  POST $API_URL ━━━━━━━━━━━━━━━━━━━━━━━━━"
PAY_PARAMS=$(jq -n --arg url "$API_URL" --argjson body "$API_BODY" \
    '{name:"aceguard_pay_for_api",arguments:{url:$url,method:"POST",json_body:$body}}')
PAY_RESULT=$(call 3 "tools/call" "$PAY_PARAMS")
echo "$PAY_RESULT" | jq -r '.result.content[0].text' | jq '. | del(.upstream_response) | . + {_upstream_status: .upstream_status}'
IS_ERROR=$(echo "$PAY_RESULT" | jq -r '.result.isError // false')
if [ "$IS_ERROR" = "true" ]; then
    echo "⚠️  pay_for_api isError=true. Likely policy rejection (allowlist / cap / paused) or upstream non-200." >&2
    exit 3
fi

echo
echo "━━━ 4. aceguard_balance (after spend) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
call 4 "tools/call" '{"name":"aceguard_balance","arguments":{}}' \
    | jq -r '.result.content[0].text' \
    | jq '{balance_usdc, daily_remaining_usdc, paused}'

echo
echo "✅ done."
