<# Diagnostic raw UDP forwarding only; no official results or timing commands. #>
[CmdletBinding()]
param(
    [string]$TargetIP = "10.227.186.166",
    [ValidateRange(1,65535)][int]$Port = 26,
    [ValidateRange(1,600)][int]$Seconds = 300
)
$ErrorActionPreference = "Stop"
$finsTargetAddress = [System.Net.IPAddress]::Parse($TargetIP)
if ($finsTargetAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "TargetIP must be an IPv4 address."
}
$finsLocalAddresses = @("127.0.0.1")
$finsLocalAddresses += @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
if ($finsLocalAddresses -contains $finsTargetAddress.IPAddressToString) {
    throw "Run this relay on the SwimTime computer. TargetIP must be the FINS computer."
}
$finsReceiver = $null
$finsSender = $null
$finsReceived = 0
$finsSent = 0
$finsRejected = 0
$finsStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$finsLastReport = -10
$finsLog = Join-Path $PSScriptRoot ("relay-" + (Get-Date -Format "yyyyMMdd-HHmmss-ffff") + ".log")
function Write-FinsLog([string]$Message) {
    $finsLine = (Get-Date -Format "o") + " " + $Message
    Write-Host $finsLine
    Add-Content -LiteralPath $finsLog -Value $finsLine -Encoding UTF8
}
try {
    $finsReceiver = [System.Net.Sockets.UdpClient]::new([System.Net.Sockets.AddressFamily]::InterNetwork)
    $finsReceiver.Client.ExclusiveAddressUse = $true
    $finsReceiver.Client.ReceiveTimeout = 500
    $finsEndpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, $Port)
    $finsReceiver.Client.Bind($finsEndpoint)
    $finsSender = [System.Net.Sockets.UdpClient]::new([System.Net.Sockets.AddressFamily]::InterNetwork)
    Write-FinsLog "DIAGNOSTIC TEST. Listen UDP $Port. Forward exact bytes to ${TargetIP}:$Port."
    Write-FinsLog "In SwimTime select Enable display via network + Send only local, then OK."
    Write-FinsLog "UDP send counts show local send attempts; delivery must be confirmed on FINS."
    while ($finsStopwatch.Elapsed.TotalSeconds -lt $Seconds) {
        $finsPeer = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
        try {
            [byte[]]$finsBytes = $finsReceiver.Receive([ref]$finsPeer)
            $finsReceived++
            if (($finsLocalAddresses -contains $finsPeer.Address.IPAddressToString) -or
                [System.Net.IPAddress]::IsLoopback($finsPeer.Address)) {
                $finsSentBytes = $finsSender.Send($finsBytes, $finsBytes.Length, $TargetIP, $Port)
                if ($finsSentBytes -ne $finsBytes.Length) { throw "Unexpected UDP send length" }
                $finsSent++
            } else {
                $finsRejected++
            }
        } catch {
            $finsSocketError = $_.Exception
            while ($null -ne $finsSocketError.InnerException) {
                $finsSocketError = $finsSocketError.InnerException
            }
            if (($finsSocketError -isnot [System.Net.Sockets.SocketException]) -or
                $finsSocketError.SocketErrorCode -ne [System.Net.Sockets.SocketError]::TimedOut) { throw }
        }
        if ($finsStopwatch.Elapsed.TotalSeconds - $finsLastReport -ge 5) {
            Write-FinsLog "received=$finsReceived sent=$finsSent rejected_remote_source=$finsRejected"
            $finsLastReport = $finsStopwatch.Elapsed.TotalSeconds
        }
    }
} catch {
    Write-FinsLog ("ERROR: " + $_.Exception.Message)
    Write-FinsLog "If UDP 26 is occupied, identify its owner. Do not close SwimTime or change COM settings."
    throw
} finally {
    if ($null -ne $finsReceiver) { $finsReceiver.Close() }
    if ($null -ne $finsSender) { $finsSender.Close() }
    Write-FinsLog "STOPPED received=$finsReceived sent=$finsSent rejected_remote_source=$finsRejected"
}
