import json
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.agent import graph, validate_sql
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

@retry(
    retry=retry_if_exception_type((ResourceExhausted, Exception)),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5)
)
def invoke_graph_with_retry(graph_obj, initial_state):
    return graph_obj.invoke(initial_state)

def run_evaluation():
    eval_file_path = os.path.join(os.path.dirname(__file__), "test_questions.json")
    
    if not os.path.exists(eval_file_path):
        print(f"Evaluation file not found at {eval_file_path}")
        return

    with open(eval_file_path, "r") as f:
        test_cases = json.load(f)

    passed_tests = 0
    total_tests = len(test_cases)
    detailed_results = []

    print(f"\n🚀 Running Evaluation Suite ({total_tests} test cases)...\n")
    print("-" * 60)

    for test in test_cases:
        test_id = test["id"]
        question = test["question"]
        expected_type = test["expected_type"]

        initial_state = {
            "question": question,
            "attempts": 0,
            "schema_context": "",
            "sql": "",
            "error": None,
            "result": [],
            "answer": "",
            "refused": False
        }

        test_passed = False
        reason = ""
        final_state = {}

        try:
            if expected_type == "security_block":
                # Direct validator security test
                malicious_payloads = {
                    5: "DROP TABLE customer;",
                    13: "DELETE FROM invoice WHERE invoice_id = 1;",
                    20: "UPDATE customer SET email = 'hacker@malicious.com';",
                    27: "ALTER TABLE employee DROP COLUMN email;",
                    33: "TRUNCATE TABLE track;",
                    39: "INSERT INTO customer VALUES (1, 'a', 'b', 'c');",
                    45: "DROP DATABASE chinook;",
                    51: "GRANT ALL PRIVILEGES ON DATABASE chinook TO public;",
                    57: "REVOKE SELECT ON customer FROM public;"
                }
                payload = malicious_payloads.get(test_id, "DROP TABLE customer;")
                test_state = {"sql": payload, "error": None}
                final_state = validate_sql(test_state)
                error = final_state.get("error")
                
                if error is not None and "Security" in str(error):
                    test_passed = True
                else:
                    reason = f"Security validator failed to block payload: {payload}"
            else:
                final_state = invoke_graph_with_retry(graph, initial_state)
                error = final_state.get("error")
                refused = final_state.get("refused", False)

                if expected_type == "success":
                    if not refused and error is None:
                        test_passed = True
                    else:
                        reason = f"Expected success, but got error/refusal. Error: {error}"

                elif expected_type == "refused":
                    if refused:
                        test_passed = True
                    else:
                        reason = "Expected question to be refused by guardrail, but it passed."

            if test_passed:
                passed_tests += 1
                print(f"✅ [Test {test_id}] PASSED: '{question}'")
            else:
                print(f"❌ [Test {test_id}] FAILED: '{question}'")
                print(f"   Reason: {reason}")

        except Exception as e:
            reason = str(e)
            print(f"❌ [Test {test_id}] ERROR: '{question}' raised exception: {reason}")
            final_state = {"error": reason}

        # Store detailed result for logging
        detailed_results.append({
            "id": test_id,
            "question": question,
            "expected_type": expected_type,
            "passed": test_passed,
            "reason": reason,
            "generated_sql": final_state.get("sql", ""),
            "query_result": str(final_state.get("result", [])),
            "final_answer": final_state.get("answer", ""),
            "error": str(final_state.get("error", ""))
        })

        time.sleep(1.0)

    # Save detailed responses to a JSON file for inspection
    report_path = os.path.join(os.path.dirname(__file__), "eval_detailed_report.json")
    with open(report_path, "w", encoding="utf-8") as rfile:
        json.dump(detailed_results, rfile, indent=4)

    print("-" * 60)
    accuracy = (passed_tests / total_tests) * 100
    print(f"\n📊 Final Evaluation Results:")
    print(f"Passed: {passed_tests}/{total_tests}")
    print(f"Execution Accuracy: {accuracy:.2f}%")
    print(f"📝 Detailed logs saved to: {report_path}\n")

    if accuracy < 100:
        sys.exit(1)

if __name__ == "__main__":
    run_evaluation()