# Vyom contracts

`python/cloud_compass_contracts/v1.py` is the versioned, provider-neutral
Pydantic source for cross-service contracts. `app/src/contracts/v1.ts` is the
matching browser representation. Neither file authorizes a caller to select a
tenant or role: request middleware will create `TenantContext` only after token
verification and server-side membership resolution.

Run the contract suite after installing its isolated dependencies:

```bash
python -m pip install -r contracts/python/requirements.txt
PYTHONPATH=contracts/python python -m pytest contracts/python/tests
```

When a v1 model changes, update the matching TypeScript type in the same change
and preserve the existing fields until a versioned migration is available.
