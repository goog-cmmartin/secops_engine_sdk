# Developer Checklist

## First Time Setup

After cloning the repository, complete these steps:

### 1. Initialize Submodules

```bash
# Option A: Clone with submodules
git clone --recurse-submodules https://github.com/google/secops_engine_sdk.git

# Option B: Initialize after clone
git clone https://github.com/google/secops_engine_sdk.git
cd secops_engine_sdk
git submodule update --init --recursive
```

### 2. Verify Proto Schemas

```bash
# Should show "✓ SUCCESS" with 12 proto files
python3 scripts/verify_proto_schemas.py
```

### 3. Install Dependencies

```bash
# Install SDK and examples
pip install -e .
pip install -r examples/requirements.txt
```

### 4. Configure Credentials

```bash
# Choose ONE method:

# Method 1: Service account JSON
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Method 2: Environment variables
export SECOPS_PROJECT_ID="your-project-id"
export SECOPS_CUSTOMER_ID="your-customer-id"  
export SECOPS_REGION="us"  # or "europe", "asia-southeast1"
```

### 5. Verify Installation

```bash
# Test basic SDK functionality
python3 examples/basic_search_demo.py

# Test proto schema integration
python3 examples/dashboard_query_proto_demo.py all
```

## Before Each Commit

### Pre-Commit Checklist

- [ ] **Run tests:** `python3 -m pytest tests/ -v`
- [ ] **Verify protos:** `python3 scripts/verify_proto_schemas.py`
- [ ] **Check code style:** `black . && ruff check .` (if configured)
- [ ] **Update docs:** If adding features, update relevant docs
- [ ] **Test examples:** Run any modified example scripts

### Common Workflows

#### Adding a New Query Example

1. Identify proto schema in `protos/secops_protos/protos/`
2. Add query capability to `engine/query_capabilities.py` if needed
3. Create example in `examples/` with validation
4. Update `examples/README.md` with reference
5. Test: `python3 examples/your_new_example.py`

#### Updating Proto Schemas

```bash
# Get latest proto definitions
git submodule update --remote protos/secops_protos

# Verify nothing broke
python3 scripts/verify_proto_schemas.py
python3 -m pytest tests/ -v

# Commit the update
git add protos/secops_protos
git commit -m "chore: Update secops_protos to latest"
```

#### Adding a New Proto to Dashboard Query

1. Edit `engine/query_capabilities.py`:
   ```python
   DASHBOARD_QUERY_PROTOS.add("your_new_proto")
   DASHBOARD_TO_PROTO_MAP["your_new_proto"] = "your_new_proto.proto"
   ```

2. Add validation example to `examples/dashboard_query_proto_demo.py`

3. Verify: `python3 scripts/verify_proto_schemas.py`

4. Document in `docs/proto-schemas.md`

## Troubleshooting

### "Proto directory not found"

```bash
# Initialize submodules
git submodule update --init --recursive

# Verify
ls protos/secops_protos/protos/
```

### "Submodule path contains modified content"

```bash
# Check submodule status
git submodule status

# Reset submodule to committed version
git submodule update --init --force
```

### "ImportError: No module named 'engine'"

```bash
# Ensure in project root
cd /path/to/secops_engine_sdk

# Install in editable mode
pip install -e .
```

### Credential Errors

```bash
# Verify environment variables
echo $GOOGLE_APPLICATION_CREDENTIALS
echo $SECOPS_PROJECT_ID

# Test gcloud auth
gcloud auth application-default print-access-token
```

## Testing Against Multiple Tenants

See [`docs/multi-tenant-testing.md`](multi-tenant-testing.md) for configuration patterns.

Quick example:

```python
from engine import SecOpsEngine

# Tenant A (US)
engine_us = SecOpsEngine(
    project_id="project-a",
    customer_id="customer-a",
    region="us"
)

# Tenant B (Europe)
engine_eu = SecOpsEngine(
    project_id="project-b",
    customer_id="customer-b",
    region="europe"
)
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Checkout with submodules
  uses: actions/checkout@v4
  with:
    submodules: recursive

- name: Verify proto schemas
  run: python3 scripts/verify_proto_schemas.py

- name: Run tests
  run: python3 -m pytest tests/ -v
  env:
    SECOPS_PROJECT_ID: ${{ secrets.SECOPS_PROJECT_ID }}
    SECOPS_CUSTOMER_ID: ${{ secrets.SECOPS_CUSTOMER_ID }}
    SECOPS_REGION: us
```

## Documentation Standards

When contributing documentation:

1. **Cross-link aggressively:** Use relative links between docs
2. **Include examples:** Show code, not just prose
3. **Validate commands:** Test every command in the doc
4. **Keep current:** Update when behavior changes

### Doc File Structure

```
docs/
├── DEVELOPER_CHECKLIST.md   ← This file (setup/workflow)
├── PROTO_INTEGRATION.md      ← Architecture overview
├── proto-schemas.md          ← Proto reference table
├── viewing-proto-schemas.md  ← Practical browsing guide
└── multi-tenant-testing.md   ← Multi-tenant patterns
```

## Getting Help

1. **Check examples:** `examples/` contains working code for common tasks
2. **Read protos:** `protos/secops_protos/protos/` shows available fields
3. **Run verification:** `scripts/verify_proto_schemas.py` validates config
4. **File issues:** GitHub Issues for bugs/features
5. **Internal support:** Reach out to SecOps SDK team

## Quick Reference

| Task | Command |
|------|---------|
| Verify setup | `python3 scripts/verify_proto_schemas.py` |
| Run tests | `python3 -m pytest tests/ -v` |
| Update protos | `git submodule update --remote protos/secops_protos` |
| View proto | `cat protos/secops_protos/protos/udm.proto` |
| Run example | `python3 examples/basic_search_demo.py` |
| Check git status | `git status && git submodule status` |
