# Python writes UTF-8 without BOM, including under Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$writer = Join-Path $PSScriptRoot '../../scripts/write_inventory.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $writer
} else {
    & python $writer
}
if ($LASTEXITCODE -ne 0) { throw 'Inventory was not updated. Check tofu output.' }
