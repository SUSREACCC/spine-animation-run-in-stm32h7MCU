param([string]$Port="COM11",[int]$Baud=115200,[int]$Seconds=8)
$ErrorActionPreference="Stop"
$sp = New-Object System.IO.Ports.SerialPort
$sp.PortName=$Port; $sp.BaudRate=$Baud; $sp.Parity=[System.IO.Ports.Parity]::None
$sp.DataBits=8; $sp.StopBits=[System.IO.Ports.StopBits]::One
$sp.Handshake=[System.IO.Ports.Handshake]::None
$sp.DtrEnable=$false; $sp.RtsEnable=$false
$sp.ReadTimeout=200
$bytes = New-Object System.Collections.Generic.List[byte]
$sw=[System.Diagnostics.Stopwatch]::StartNew()
$sp.Open()
$buf = New-Object byte[] 4096
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
  try { $n = $sp.Read($buf,0,$buf.Length); for($i=0;$i -lt $n;$i++){ $bytes.Add($buf[$i]) } } catch [System.TimeoutException] {}
}
$sp.Close(); $sp.Dispose()
Write-Output ("bytes={0}" -f $bytes.Count)
if ($bytes.Count -gt 0) {
  $txt = -join ($bytes | ForEach-Object { if ($_ -ge 32 -and $_ -lt 127) { [char]$_ } else { "." } })
  Write-Output ("ascii: " + $txt.Substring(0, [Math]::Min(400, $txt.Length)))
}
