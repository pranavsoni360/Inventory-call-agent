import requests

base = "http://localhost:8000"
sid  = "test_api_2"

def chat(msg):
    r = requests.post(f"{base}/chat", json={"session_id": sid, "message": msg})
    d = r.json()
    print(f"You:   {msg}")
    print(f"Agent: {d['response']}")
    print(f"Phase: {d['phase']} | Cart items: {len(d['cart'])}")
    print()

print("=== Full conversation test ===")
chat("rice 5 kg")
chat("yes")
chat("dal 2 kg")
chat("yes")
chat("show cart")
chat("confirm order")
chat("yes")

print("=== Health check ===")
print(requests.get(f"{base}/health").json())

print("\n=== Recent orders ===")
orders = requests.get(f"{base}/orders").json()
print(f"Total orders: {orders['count']}")
if orders["orders"]:
    print(f"Latest order ID: {orders['orders'][0]['order_id']}")