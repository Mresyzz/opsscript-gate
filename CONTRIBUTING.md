# Contributing to OpsScript Gate

Thank you for your interest in contributing to **OpsScript Gate**! We welcome bug reports, compatibility test fixtures, feature suggestions, and pull requests.

---

## 🛠️ Development Setup

OpsScript Gate requires **Python 3.10+** and a standard virtual environment.

```bash
# Clone the repository
git clone https://github.com/Mresyzz/opsscript-gate.git
cd opsscript-gate

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in editable mode with test dependencies
pip install -e .[test]
```

---

## 🧪 Running Tests

We maintain strict test suite isolation:
- **Unit tests with Mocking**: Run in sub-seconds and do **not** require a running Docker daemon.
- **Integration tests**: Labeled with `@pytest.mark.integration` and test against live Docker containers.

```bash
# Run unit tests (Mocked, recommended for daily development)
pytest -v -m "not integration"

# Run full test suite including live Docker integration tests
pytest -v
```

All pull requests must pass the unit test suite with 100% success rate.

---

## 🛡️ Core Security Red Lines (Strictly Enforced)

Any changes affecting the container runner **must strictly adhere** to the following security boundaries:

1. **Never use privileged containers**:
   - `privileged` must remain `False`.
   - `cap_drop` must remain `["ALL"]`.
   - `security_opt` must include `["no-new-privileges:true"]`.
2. **Read-only script mounting**:
   - Target scripts must always be mounted in read-only mode (`:ro`).
   - Never mount sensitive host paths (e.g. `/var/run/docker.sock`, `/etc`, `/sys`, `/proc`).
3. **Hard timeouts and zero-zombie cleanup**:
   - Containers must be terminated with `container.kill()` upon reaching timeout limits.
   - Resource cleanup (`container.remove(force=True)`) must be executed inside a `finally` block to prevent orphaned containers.
4. **Anti-hang non-interactive execution**:
   - Standard input must remain detached (`stdin_open=False`, `tty=False`) and bound to `/dev/null`.
   - Always inject `DEBIAN_FRONTEND=noninteractive` and `CI=true`.
5. **Modest feature scope**:
   - Do not attempt to emulate systemd, cgroups, or real network firewalls inside containers. Focus on basic script execution, command availability, and non-zero exit codes.

---

## 📦 Adding a New Linux Distribution to the Matrix

To propose or add a new distribution image:
1. Ensure the official image is available on Docker Hub and is publicly accessible.
2. Confirm the image contains `/bin/sh` for minimal POSIX execution.
3. Add a representative compatibility test fixture in `tests/fixtures/` demonstrating standard behavior.
4. Ensure the image does not require interactive initialization.

---

## 📝 Pull Request Workflow

1. Fork the repository and create a descriptive feature branch from `main`.
2. Make your modifications, adhering to standard Python formatting (PEP 8) and type hints.
3. Add or update unit tests in `tests/test_runner.py` verifying both success and failure paths.
4. Verify tests pass locally: `pytest -v -m "not integration"`.
5. Open a Pull Request against the `main` branch with a clear summary of changes.
