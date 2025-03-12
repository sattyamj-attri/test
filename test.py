from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_stream():
    with client.stream("POST", "/stream", json={"message": "Write a Code of Quick Sort."}) as response:
        for line in response.iter_lines():
            if line:
                # No need to decode; line is already a str.
                print(line)

if __name__ == "__main__":
    test_stream()
