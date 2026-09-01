# Hardware Adapter Interface (Contract)

ZeroTwin’s simulated nodes implement this contract. A real companion computer (Jetson, RPi, or equivalent) should satisfy the same surface so it can join the federation later without redesigning the learning path.

This document is an **interface specification**, not a shipping driver.

---

## Responsibilities of an edge node

1. **Sense** — Obtain windows of vibration, temperature, voltage, and (optional) acoustic or equivalent PHM-relevant channels.  
2. **Keep data local** — Never upload raw windows to the aggregation server.  
3. **Train / fine-tune** — Run the local PHM model on recent windows.  
4. **Export update** — Produce model parameters (or delta) after local steps.  
5. **Sign** — Sign the parameter payload with the node’s Ed25519 key.  
6. **Send** — Transmit only the signed parameter message to the aggregation endpoint when connectivity exists.  
7. **Receive** — Apply the global model returned by aggregation.  
8. **Report health** (optional) — Local inference for the Command Center or onboard alerts; still no raw stream upload required for federation.

---

## Message types (logical)

### Node → Server: `ModelUpdate`

```text
node_id: string
round_hint: int (optional)
parameters: ordered list of tensors / ndarrays (model state)
signature: bytes (Ed25519 over hash of canonical parameter encoding)
```

### Server → Node: `GlobalModel`

```text
round: int
parameters: ordered list of tensors / ndarrays
```

Encoding in the reference testbed follows Flower’s parameter exchange. A hardware node may use the same Flower client API or an equivalent gRPC/REST bridge that preserves “parameters only + signature.”

---

## Connectivity assumptions

- Intermittent IP reachability to the aggregation host is enough.  
- Long gaps are allowed; the testbed evaluates delayed aggregation.  
- The adapter does **not** require continuous high-bandwidth telemetry uplink.

---

## Out of scope for this contract

- PX4/ArduPilot flight mode management  
- MAVLink command authority  
- Radio waveform or mesh routing  
- Airworthiness or regulatory approval  

Those belong to vehicle integration projects that consume this contract.

---

## Minimal compliance checklist

- [ ] Local dataset or ring buffer of sensor windows  
- [ ] Local training step producing updated weights  
- [ ] No raw window upload in the federation path  
- [ ] Signature over parameter payload  
- [ ] Ability to load global weights from aggregation  
- [ ] Documented node_id and key management  

When all boxes are checked, the node is a ZeroTwin edge participant in the architectural sense.
