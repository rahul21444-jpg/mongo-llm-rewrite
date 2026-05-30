"""Generate a synthetic analytics dataset in the throwaway `poc_aggrewrite` DB.

Deliberately ships NO secondary indexes so unindexed $match/$lookup pipelines are
realistically slow -- that headroom is what query rewriting reclaims.
Reproducible: fixed RNG seed.
"""
import os
import random
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:47017")

random.seed(42)

REGIONS = ["NA", "EU", "APAC", "LATAM", "MEA"]
TIERS = ["bronze", "silver", "gold", "platinum"]
# ~8% cancelled -> predicate pushdown on status is a big selectivity win
STATUSES = ["delivered"] * 55 + ["shipped"] * 20 + ["pending"] * 17 + ["cancelled"] * 8
SKUS = [f"SKU-{i:04d}" for i in range(500)]

N_CUST = 5_000
N_ORDERS = 200_000
BATCH = 10_000


def main():
    db = MongoClient(MONGO_URI)["poc_aggrewrite"]
    db.customers.drop()
    db.orders.drop()

    customers = [
        {
            "_id": cid,
            "region": random.choice(REGIONS),
            "tier": random.choice(TIERS),
            "signup_year": random.randint(2015, 2025),
        }
        for cid in range(1, N_CUST + 1)
    ]
    db.customers.insert_many(customers)
    print(f"inserted {db.customers.count_documents({})} customers")

    batch = []
    for oid in range(1, N_ORDERS + 1):
        items = [
            {"sku": random.choice(SKUS), "qty": random.randint(1, 10)}
            for _ in range(random.randint(1, 5))
        ]
        batch.append(
            {
                "_id": oid,
                "customer_id": random.randint(1, N_CUST),
                "status": random.choice(STATUSES),
                "amount": round(random.uniform(5, 500), 2),
                "items": items,
                "order_year": random.randint(2020, 2025),
            }
        )
        if len(batch) >= BATCH:
            db.orders.insert_many(batch)
            batch = []
    if batch:
        db.orders.insert_many(batch)

    print(f"inserted {db.orders.count_documents({})} orders")
    print("orders indexes (only _id expected):", list(db.orders.index_information().keys()))


if __name__ == "__main__":
    main()
