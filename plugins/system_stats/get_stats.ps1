# Скрипт для получения данных из LibreHardwareMonitorLib.dll (v2)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$DllPath = Join-Path $ScriptDir "bin\LibreHardwareMonitorLib.dll"



try {
    Add-Type -Path $DllPath
} catch {
    Write-Error "Не удалось загрузить DLL: $_"
    exit 1
}

$Computer = New-Object LibreHardwareMonitor.Hardware.Computer
$Computer.IsCpuEnabled = $true
$Computer.IsGpuEnabled = $true

try {
    $Computer.Open()
    
    $Stats = @{
        cpu_temp = 0
        gpu_temp = 0
        gpu_load = 0
        cpu_load = 0
    }

    foreach ($hardware in $Computer.Hardware) {
        $hardware.Update()
        
        # CPU Monitoring
        if ($hardware.HardwareType -eq "Cpu") {
            $Stats.cpu_name = $hardware.Name
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq "Temperature") {
                    if ($sensor.Name -match "Package|Tdie|Tctl|Core Average|Core #|Core Max|CPU Package|Core \(") {
                        if ($Stats.cpu_temp -eq 0 -or $sensor.Value -gt $Stats.cpu_temp) {
                            $Stats.cpu_temp = [Math]::Round($sensor.Value, 0)
                        }
                    }
                }
                if ($sensor.SensorType -eq "Load" -and $sensor.Name -match "Total") {
                    $Stats.cpu_load = [Math]::Round($sensor.Value, 0)
                }
            }
        }
        
        # GPU Monitoring
        if ($hardware.HardwareType -match "Gpu") {
            $Stats.gpu_name = $hardware.Name
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq "Temperature" -and $sensor.Name -match "Core") {
                    $Stats.gpu_temp = [Math]::Round($sensor.Value, 0)
                }
                if ($sensor.SensorType -eq "Load" -and $sensor.Name -match "Core") {
                    $Stats.gpu_load = [Math]::Round($sensor.Value, 0)
                }
            }
        }

        # Storage Monitoring
        if ($hardware.HardwareType -match "Storage") {
            if (-not $Stats.disk_temps) { $Stats.disk_temps = @() }
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq "Temperature") {
                    $Stats.disk_temps += @{
                        name = $hardware.Name
                        value = [Math]::Round($sensor.Value, 0)
                    }
                }
            }
        }
    }

    $Stats | ConvertTo-Json -Compress
} finally {
    $Computer.Close()
}
