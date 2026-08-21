$ErrorActionPreference = "Stop"

function Write-CyberAILocalStep([string] $Message) {
    Write-Host "[cyberai-local] $Message"
}

function ConvertTo-NormalizedPathFragment([string] $Path) {
    return ([System.IO.Path]::GetFullPath([string] $Path)).TrimEnd("\").ToLowerInvariant()
}

function ConvertTo-PowerShellSingleQuotedString([string] $Value) {
    return "'" + ($Value -replace "'", "''") + "'"
}

function Get-ProcessInfoById([int] $ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    return [pscustomobject]@{
        ProcessId = [int] $process.ProcessId
        ParentProcessId = [int] $process.ParentProcessId
        Name = [string] $process.Name
        CommandLine = [string] $process.CommandLine
        ExecutablePath = [string] $process.ExecutablePath
    }
}

function Get-CurrentProcessLineageIds {
    $ids = New-Object System.Collections.Generic.List[int]
    $current = Get-ProcessInfoById -ProcessId $PID
    while ($current) {
        $ids.Add([int] $current.ProcessId)
        if ($current.ParentProcessId -le 0) {
            break
        }
        $current = Get-ProcessInfoById -ProcessId $current.ParentProcessId
    }
    return $ids.ToArray()
}

function Test-CyberAIProcess(
    [Parameter(Mandatory = $true)] $ProcessInfo,
    [Parameter(Mandatory = $true)] [string] $Root
) {
    $rootFragment = ConvertTo-NormalizedPathFragment $Root
    $haystack = @(
        [string] $ProcessInfo.CommandLine,
        [string] $ProcessInfo.ExecutablePath
    ) -join " "
    if (-not $haystack.Trim()) {
        return $false
    }
    $normalizedHaystack = $haystack.ToLowerInvariant()
    if ($normalizedHaystack.Contains($rootFragment)) {
        return $true
    }

    $isLegacyApiWrapper = $normalizedHaystack.Contains("cyberai.main:create_app") -and
        $normalizedHaystack.Contains("--port 8001")
    $isLegacyWebWrapper = $normalizedHaystack.Contains("api_proxy_target") -and
        $normalizedHaystack.Contains("localhost:8001") -and
        $normalizedHaystack.Contains("npm run dev") -and
        $normalizedHaystack.Contains("--port 3000")
    return $isLegacyApiWrapper -or $isLegacyWebWrapper
}

function Get-ProcessTree([int] $ProcessId) {
    $allProcesses = @(Get-CimInstance Win32_Process)
    $byParent = @{}
    foreach ($process in $allProcesses) {
        $parentId = [int] $process.ParentProcessId
        if (-not $byParent.ContainsKey($parentId)) {
            $byParent[$parentId] = New-Object System.Collections.Generic.List[object]
        }
        $byParent[$parentId].Add($process)
    }

    $result = New-Object System.Collections.Generic.List[object]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $seen = @{}
    $queue.Enqueue($ProcessId)

    while ($queue.Count -gt 0) {
        $currentId = $queue.Dequeue()
        if ($seen.ContainsKey($currentId)) {
            continue
        }
        $seen[$currentId] = $true

        $current = $allProcesses | Where-Object { [int] $_.ProcessId -eq $currentId } | Select-Object -First 1
        if ($current) {
            $result.Add([pscustomobject]@{
                ProcessId = [int] $current.ProcessId
                ParentProcessId = [int] $current.ParentProcessId
                Name = [string] $current.Name
                CommandLine = [string] $current.CommandLine
                ExecutablePath = [string] $current.ExecutablePath
            })
        }

        if ($byParent.ContainsKey($currentId)) {
            foreach ($child in $byParent[$currentId]) {
                $queue.Enqueue([int] $child.ProcessId)
            }
        }
    }

    return $result.ToArray()
}

function Get-ListeningProcess([int] $Port) {
    $connections = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    $seen = @{}
    $processes = New-Object System.Collections.Generic.List[object]
    foreach ($connection in $connections) {
        $ownerPid = [int] $connection.OwningProcess
        if ($seen.ContainsKey($ownerPid)) {
            continue
        }
        $seen[$ownerPid] = $true
        $process = Get-ProcessInfoById -ProcessId $ownerPid
        if ($process) {
            $processes.Add($process)
        }
    }
    return $processes.ToArray()
}

function Find-CyberAIProcessRoot(
    [int] $ProcessId,
    [string] $Root
) {
    $current = Get-ProcessInfoById -ProcessId $ProcessId
    $candidate = $null
    while ($current) {
        if (Test-CyberAIProcess -ProcessInfo $current -Root $Root) {
            $candidate = $current
        } elseif ($candidate) {
            break
        }

        if ($current.ParentProcessId -le 0) {
            break
        }
        $current = Get-ProcessInfoById -ProcessId $current.ParentProcessId
    }
    return $candidate
}

function Format-ProcessSummary($ProcessInfo) {
    return "PID: $($ProcessInfo.ProcessId)`nName: $($ProcessInfo.Name)`nCommandLine: $($ProcessInfo.CommandLine)"
}

function Format-ExternalProcessMessage([int] $Port, $ProcessInfo) {
    return @"
Port $Port is owned by an external process.
$(Format-ProcessSummary $ProcessInfo)
Refusing to terminate it.
"@
}

function Stop-CyberAIProcessTree(
    [int] $ProcessId,
    [string] $Name,
    [string] $Root,
    [int[]] $ExcludeProcessIds = @()
) {
    $process = Get-ProcessInfoById -ProcessId $ProcessId
    if (-not $process) {
        return
    }

    $rootProcess = Find-CyberAIProcessRoot -ProcessId $ProcessId -Root $Root
    if (-not $rootProcess) {
        Write-CyberAILocalStep "$Name PID $ProcessId is not identifiable as CyberAI; refusing to terminate it."
        return
    }

    if ($ExcludeProcessIds -contains [int] $rootProcess.ProcessId) {
        Write-CyberAILocalStep "Skipping current $Name process tree rooted at PID $($rootProcess.ProcessId)."
        return
    }

    Write-CyberAILocalStep "Stopping CyberAI $Name process tree rooted at PID $($rootProcess.ProcessId)."
    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        & $taskkill.Source /PID $rootProcess.ProcessId /T /F | Out-Null
    } else {
        $tree = @(Get-ProcessTree -ProcessId $rootProcess.ProcessId)
        foreach ($treeProcess in ($tree | Sort-Object ProcessId -Descending)) {
            if ($ExcludeProcessIds -contains [int] $treeProcess.ProcessId) {
                continue
            }
            Stop-Process -Id $treeProcess.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Clear-StalePidFile(
    [string] $Path,
    [string] $Name,
    [string] $Root,
    [int[]] $ExcludeProcessIds = @()
) {
    if (-not (Test-Path $Path)) {
        return
    }

    $rawPid = (Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $rawPid) {
        Remove-Item -LiteralPath $Path -Force
        return
    }

    $parsedPid = 0
    if (-not [int]::TryParse(([string] $rawPid).Trim(), [ref] $parsedPid)) {
        Write-CyberAILocalStep "Removing invalid $Name PID file: $Path"
        Remove-Item -LiteralPath $Path -Force
        return
    }

    $process = Get-ProcessInfoById -ProcessId $parsedPid
    if ($process) {
        $rootProcess = Find-CyberAIProcessRoot -ProcessId $parsedPid -Root $Root
        if ($rootProcess) {
            Write-CyberAILocalStep "Found stale CyberAI $Name process PID $parsedPid."
            Stop-CyberAIProcessTree -ProcessId $parsedPid -Name $Name -Root $Root -ExcludeProcessIds $ExcludeProcessIds
        } else {
            Write-CyberAILocalStep "$Name PID file points to an external process; removing stale PID file without terminating it."
            Write-CyberAILocalStep (Format-ProcessSummary $process)
        }
    }

    Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
}

function Wait-PortFree([int] $Port, [int] $TimeoutSeconds = 15) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $listeners = @(Get-ListeningProcess -Port $Port)
        if ($listeners.Count -eq 0) {
            Write-CyberAILocalStep "Port $Port is free."
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for port $Port to become free."
}

function Stop-CyberAIListenersOnPort(
    [int] $Port,
    [string] $Name,
    [string] $Root,
    [int[]] $ExcludeProcessIds = @(),
    [switch] $FailOnExternal
) {
    $listeners = @(Get-ListeningProcess -Port $Port)
    foreach ($listener in $listeners) {
        $rootProcess = Find-CyberAIProcessRoot -ProcessId $listener.ProcessId -Root $Root
        if ($rootProcess) {
            Write-CyberAILocalStep "Found stale CyberAI $Name listener PID $($listener.ProcessId) on port $Port."
            Stop-CyberAIProcessTree -ProcessId $listener.ProcessId -Name $Name -Root $Root -ExcludeProcessIds $ExcludeProcessIds
        } elseif ($FailOnExternal) {
            throw (Format-ExternalProcessMessage -Port $Port -ProcessInfo $listener)
        } else {
            Write-CyberAILocalStep (Format-ExternalProcessMessage -Port $Port -ProcessInfo $listener)
        }
    }
}

function Stop-CyberAIOrphanProcesses(
    [string] $Root,
    [int[]] $ExcludeProcessIds = @()
) {
    $allowedNames = @(
        "cmd.exe",
        "node.exe",
        "npm.cmd",
        "powershell.exe",
        "pwsh.exe",
        "python.exe",
        "python3.exe",
        "uv.exe"
    )
    $allProcesses = @(Get-CimInstance Win32_Process)
    $candidates = @(
        $allProcesses | Where-Object {
            $info = [pscustomobject]@{
                ProcessId = [int] $_.ProcessId
                ParentProcessId = [int] $_.ParentProcessId
                Name = [string] $_.Name
                CommandLine = [string] $_.CommandLine
                ExecutablePath = [string] $_.ExecutablePath
            }
            ($allowedNames -contains $info.Name) -and
                (-not ($ExcludeProcessIds -contains [int] $info.ProcessId)) -and
                (Test-CyberAIProcess -ProcessInfo $info -Root $Root)
        }
    )

    foreach ($candidate in $candidates) {
        if ($ExcludeProcessIds -contains [int] $candidate.ProcessId) {
            continue
        }
        $hasCyberAIParent = $false
        $parent = Get-ProcessInfoById -ProcessId ([int] $candidate.ParentProcessId)
        while ($parent) {
            if ($candidates.ProcessId -contains [int] $parent.ProcessId) {
                $hasCyberAIParent = $true
                break
            }
            if ($parent.ParentProcessId -le 0) {
                break
            }
            $parent = Get-ProcessInfoById -ProcessId $parent.ParentProcessId
        }
        if (-not $hasCyberAIParent) {
            Write-CyberAILocalStep "Found orphan CyberAI local process PID $($candidate.ProcessId)."
            Stop-CyberAIProcessTree -ProcessId $candidate.ProcessId -Name "orphan" -Root $Root -ExcludeProcessIds $ExcludeProcessIds
        }
    }
}

function Assert-PortAvailable(
    [int] $Port,
    [string] $Name,
    [string] $Root,
    [int[]] $ExcludeProcessIds = @()
) {
    Stop-CyberAIListenersOnPort `
        -Port $Port `
        -Name $Name `
        -Root $Root `
        -ExcludeProcessIds $ExcludeProcessIds `
        -FailOnExternal
    Wait-PortFree -Port $Port -TimeoutSeconds 15
}

function Assert-PortNotListening([int] $Port) {
    $listeners = @(Get-ListeningProcess -Port $Port)
    if ($listeners.Count -gt 0) {
        throw "Port $Port still has listener(s): $($listeners.ProcessId -join ', ')"
    }
    Write-CyberAILocalStep "Confirmed port $Port has no listener."
}
