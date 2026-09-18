# Contributing to OpsScript Gate

Thank you for your interest in contributing to **OpsScript Gate**! We welcome bug reports, compatibility test fixtures, feature suggestions, and pull requests.

---

## Development Setup

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

## Running Tests

The test suite separates mocked unit tests from Docker integration tests:
- **Unit tests**: Use mocking and do not require a running Docker daemon.
- **Integration tests**: Labeled with `@pytest.mark.integration` and run against real Docker containers.

```bash
# Run unit tests (recommended for daily development)
pytest -v -m "not integration"

# Run full test suite including live Docker integration tests
pytest -v
```

Pull requests should pass the unit test suite.

---

## Runner safety constraints

Any changes affecting the container runner should preserve these constraints:

1. **Unprivileged execution**:
   - Containers must not run with `privileged=True`.
   - `cap_drop` must remain `["ALL"]`.
   - `security_opt` must include `["no-new-privileges:true"]`.
2. **Read-only script mount**:
   - Target scripts must remain read-only (`:ro`).
   - Do not mount additional host filesystem paths into test containers.
3. **Timeout & cleanup**:
   - Containers reaching timeout limits should be terminated with `container.kill()`.
   - Container removal in `finally` blocks must be preserved.
4. **Non-interactive execution**:
   - Standard input should remain detached (`stdin_open=False`, `tty=False`, `</dev/null`).
   - Keep non-interactive environment variables (`DEBIAN_FRONTEND=noninteractive`, `CI=true`).
5. **Scope**:
   - Avoid emulating complex init systems (like systemd) inside containers; the runner focuses on standard script execution, command availability, and exit codes.

---

## Adding a New Linux Distribution

To propose or add a new distribution image:
1. Ensure the official image is available on Docker Hub and is publicly accessible.
2. Confirm the image contains `/bin/sh` for minimal POSIX execution.
3. Add a representative compatibility test fixture in `tests/fixtures/` demonstrating standard behavior.
4. Ensure the image does not require interactive initialization.

---

## Pull Request Workflow

1. Fork the repository and create a descriptive feature branch from `main`.
2. Make your modifications, adhering to standard Python formatting (PEP 8) and type hints.
3. Add or update unit tests in `tests/test_runner.py` verifying both success and failure paths.
4. Verify tests pass locally: `pytest -v -m "not integration"`.
5. Open a Pull Request against the `main` branch with a clear summary of changes.
