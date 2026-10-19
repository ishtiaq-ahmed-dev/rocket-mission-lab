# API and telemetry contract

## What it does

FastAPI exposes missions, run metadata, versioned telemetry, results, failure counts, runtime/configuration, checkpoints, and controlled training jobs. Pydantic validates physics frames and run-level outcomes. The shared JSON Schema is exported from the same Pydantic model; TypeScript declares the corresponding frontend structures and validates incoming recordings.

## Why this approach

Telemetry is inspectable JSON with SI units and wxyz quaternion order. Explicit outcome and failure_reason prevent a renderer from guessing success from animation. Run IDs are resolved through a saved index; arbitrary filesystem paths are never accepted. Local CORS allows only the frontend origins.

## Key formulas and mapping

```text
GET /missions
GET /runs?mission=landing&method=classical&level=4&seed=42
GET /runs/{id}/telemetry
GET /results/summary, /results/failures
GET /training, /checkpoints, /system, /schema/telemetry
POST /simulate, /training, /training/{id}/stop
```

## Five interview questions

1. **Why version a telemetry schema?** Consumer code must reject incompatible coordinate/order changes instead of silently drawing an incorrect flight.
2. **What is touchdown_speed for takeoff?** It is the historical common field name for terminal total speed. For takeoff it describes separation, not impact.
3. **How do you avoid file-path injection?** An ID must exist in the index before a telemetry/checkpoint path is constructed. Training arguments are a validated argument array, not a shell command string.
4. **Why save normalization separately?** A model's observation transform is part of the inference contract; weights alone are insufficient.
5. **What is the trust boundary?** This is a loopback-only personal research server without authentication, not an internet-facing multiuser service. Do not expose it publicly without a separate security design.

## Validation

Tests exercise all read endpoints, every terminal outcome, malformed requests, unknown run/checkpoint handling, schema export consistency and a stubbed bounded training dispatch. In-process API tests require normal Windows socket permissions because asyncio creates a local socketpair.
