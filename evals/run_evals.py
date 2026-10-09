import json
import os
import sys
import time

# Load .env variables so GOOGLE_API_KEY is detected when running locally
from dotenv import load_dotenv
load_dotenv()

# Add project root to path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.agent import graph

from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

# Automatically retry up to 5 times with exponential backoff if a 429 error occurs
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

        try:
            # Use the retry-backed function instead of direct graph.invoke
            final_state = invoke_graph_with_retry(graph, initial_state)
            error = final_state.get("error")
            refused = final_state.get("refused", False)
            result = final_state.get("result", [])

            # Evaluate behavior based on expected type
            test_passed = False
            reason = ""

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

            elif expected_type == "security_block":
                if error is not None and "Security" in str(error):
                    test_passed = True
                else:
                    reason = f"Expected security block by validator, but got error: {error}"

            if test_passed:
                passed_tests += 1
                print(f"✅ [Test {test_id}] PASSED: '{question}'")
            else:
                print(f"❌ [Test {test_id}] FAILED: '{question}'")
                print(f"   Reason: {reason}")

        except Exception as e:
            print(f"❌ [Test {test_id}] ERROR: '{question}' raised exception: {str(e)}")

        # Pause briefly between requests to respect API rate limits (avoids 429 errors)
        time.sleep(1.5)

    print("-" * 60)
    accuracy = (passed_tests / total_tests) * 100
    print(f"\n📊 Final Evaluation Results:")
    print(f"Passed: {passed_tests}/{total_tests}")
    print(f"Execution Accuracy: {accuracy:.2f}%\n")

    if accuracy < 100:
        sys.exit(1)  # Exit with error code so CI/CD pipelines can catch failing runs

if __name__ == "__main__":
    run_evaluation()