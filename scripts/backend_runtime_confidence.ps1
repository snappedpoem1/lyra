[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "[backend-runtime-confidence] running focused lyra-core library tests"
cargo test -p lyra-core --lib

Write-Host "[backend-runtime-confidence] running isolated app-data runtime proof"
cargo test -p lyra-core --test backend_runtime_confidence

Write-Host "[backend-runtime-confidence] backend runtime confidence checks passed"
