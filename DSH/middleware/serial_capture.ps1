param(
    [string]$Port = "COM11",
    [int]$Baud = 115200,
    [int]$Seconds = 20,
    [string]$Out = "serial.log",
    [switch]$Reset
)
# Capture USART1 output from the board (on-board CH340).
#
# IMPORTANT: on this board the CH340 modem-control lines are wired to BOOT0/NRST
# (auto-ISP style).  Measurements on STM32H743IIT6 V1.3:
#   DtrEnable = $false  -> BOOT0 high -> the MCU boots the system bootloader
#   DtrEnable = $true   -> BOOT0 low  -> normal application boot
#   RtsEnable = $true   -> NRST asserted (reset held)
# So we keep DTR asserted and RTS released, and pulse RTS to reset the board.
$ErrorActionPreference = "Stop"
$sp = New-Object System.IO.Ports.SerialPort
$sp.PortName = $Port
$sp.BaudRate = $Baud
$sp.Parity = [System.IO.Ports.Parity]::None
$sp.DataBits = 8
$sp.StopBits = [System.IO.Ports.StopBits]::One
$sp.Handshake = [System.IO.Ports.Handshake]::None
$sp.ReadTimeout = 200

$sp.Open()
$sp.DtrEnable = $true
$sp.RtsEnable = $false

if ($Reset) {
    Start-Sleep -Milliseconds 100
    $sp.RtsEnable = $true      # assert NRST
    Start-Sleep -Milliseconds 80
    $sp.RtsEnable = $false     # release -> boot application (BOOT0 low)
    Start-Sleep -Milliseconds 50
}

$bytes = New-Object System.Collections.Generic.List[byte]
$buf = New-Object byte[] 4096
$sw = [System.Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    try {
        $n = $sp.Read($buf, 0, $buf.Length)
        for ($i = 0; $i -lt $n; $i++) { $bytes.Add($buf[$i]) }
    } catch [System.TimeoutException] { }
}

$sp.Close()
$sp.Dispose()

$text = -join ($bytes | ForEach-Object { if ($_ -ge 32 -and $_ -lt 127) { [char]$_ } elseif ($_ -eq 13) { "`r" } elseif ($_ -eq 10) { "`n" } else { "." } })
$text | Out-File -FilePath $Out -Encoding utf8
Write-Output ("bytes={0}" -f $bytes.Count)
if ($bytes.Count -gt 0) { Write-Output $text }
