#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPARE_SCRIPT="${REPO_DIR}/tools/compare_runtime_traces.sh"
FIXTURE_DIR="${SCRIPT_DIR}/fixtures/runtime_trace"
TMP_DIR="$(mktemp -d /tmp/samp-runtime-trace-test.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

run_expect_status() {
  local expected="$1"
  local label="$2"
  shift 2
  local output_file="${TMP_DIR}/${label}.out"
  local status=0

  "$COMPARE_SCRIPT" "$@" >"$output_file" 2>&1 || status=$?
  if [[ "$status" -ne "$expected" ]]; then
    sed -n '1,160p' "$output_file" >&2
    fail "$label returned $status, expected $expected"
  fi
}

PASS_TRACE="${FIXTURE_DIR}/pass.log"
FAIL_TRACE="${FIXTURE_DIR}/critical_fail.log"
SHIFTED_TRACE="${FIXTURE_DIR}/shifted_base.log"

run_expect_status 0 pass \
  "$PASS_TRACE" "$PASS_TRACE" "${TMP_DIR}/pass-report"
rg -q '^ABI checks FAIL: 0$' "${TMP_DIR}/pass.out" || fail "pass report contains a FAIL"
rg -q '^Result: PASS$' "${TMP_DIR}/pass.out" || fail "pass result marker missing"

run_expect_status 5 critical-fail \
  "$PASS_TRACE" "$FAIL_TRACE" "${TMP_DIR}/fail-report"
rg -q $'^critical\tnet_recvfrom\t.*\tFAIL\t' \
  "${TMP_DIR}/fail-report/check_report.tsv" || fail "recvfrom critical failure missing"
rg -q '^Result: FAIL$' "${TMP_DIR}/critical-fail.out" || fail "failure result marker missing"

run_expect_status 0 report-only \
  --report-only "$PASS_TRACE" "$FAIL_TRACE" "${TMP_DIR}/report-only-report"
rg -Fqx 'Result: FAIL (report-only; exit status suppressed)' \
  "${TMP_DIR}/report-only.out" || fail "report-only result marker missing"

run_expect_status 0 shifted-base \
  "$PASS_TRACE" "$SHIFTED_TRACE" "${TMP_DIR}/shifted-report"
rg -q '^055A0000$' \
  "${TMP_DIR}/shifted-report/candidate_trim/samp_module_base.txt" || fail "shifted base was not detected"
rg -q $'^critical\tsamp_process_attach_call\t.*\tPASS\t' \
  "${TMP_DIR}/shifted-report/check_report.tsv" || fail "shifted attach call was not matched"
rg -q $'^critical\tsamp_process_detach_call\t.*\tPASS\t' \
  "${TMP_DIR}/shifted-report/check_report.tsv" || fail "shifted detach call was not matched"
rg -Fqx $'1\tPE_DLL_REASON.PROCESS_ATTACH' \
  "${TMP_DIR}/shifted-report/candidate_trim/call_api_counts.tsv" || fail "shifted attach API count missing"
rg -Fqx $'1\tPE_DLL_REASON.PROCESS_DETACH' \
  "${TMP_DIR}/shifted-report/candidate_trim/call_api_counts.tsv" || fail "shifted detach API count missing"

echo "PASS: compare_runtime_traces fixtures"
