# Read-only inventory. Local UDP ports do not establish the destination port.
$swimProcesses = Get-Process | Where-Object { $_.ProcessName -like '*SwimTime*' }
foreach ($swimProcess in $swimProcesses) {
    Write-Output ("SwimTime PID: " + $swimProcess.Id)
    Get-NetUDPEndpoint -OwningProcess $swimProcess.Id -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess
    Get-NetTCPConnection -OwningProcess $swimProcess.Id -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State
}
if (-not $swimProcesses) { Write-Output 'No SwimTime process found.' }
