## Description

Briefly describe the change and the motivation behind it.

## Changes Made
- 

## Security Red Lines Verification
Please check all that apply:
- [ ] No privileged container mode introduced (`privileged=False` maintained)
- [ ] Capabilities drop maintained (`cap_drop=["ALL"]`)
- [ ] `no-new-privileges:true` maintained
- [ ] Target scripts remain mounted strictly read-only (`:ro`)
- [ ] Timeout and zero-zombie container cleanup logic preserved

## Testing
- [ ] Unit tests added/updated (`pytest -v -m "not integration"`)
- [ ] All tests passing locally
