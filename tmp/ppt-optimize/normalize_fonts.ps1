param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [double]$MinimumPt = 12
)

$ErrorActionPreference = "Stop"

function Set-MinimumRunSize {
    param(
        [object]$TextRange,
        [double]$Minimum
    )

    if ($null -eq $TextRange) {
        return
    }

    $runs = $TextRange.Runs()
    if ($null -eq $runs) {
        return
    }

    foreach ($run in $runs) {
        try {
            $size = [double]$run.Font.Size
            if ($size -gt 0 -and $size -lt $Minimum) {
                $run.Font.Size = $Minimum
            }
        }
        catch {
            # Some decorative fields do not expose font properties consistently.
        }
    }
}

function Set-ShapeMinimumFont {
    param(
        [object]$Shape,
        [double]$Minimum
    )

    if ($Shape.Type -eq 6) {
        foreach ($child in $Shape.GroupItems) {
            Set-ShapeMinimumFont -Shape $child -Minimum $Minimum
        }
        return
    }

    if ($Shape.HasTable -eq -1) {
        $table = $Shape.Table
        for ($row = 1; $row -le $table.Rows.Count; $row++) {
            for ($column = 1; $column -le $table.Columns.Count; $column++) {
                $cellShape = $table.Cell($row, $column).Shape
                if ($cellShape.HasTextFrame -eq -1 -and $cellShape.TextFrame.HasText -eq -1) {
                    Set-MinimumRunSize -TextRange $cellShape.TextFrame.TextRange -Minimum $Minimum
                }
            }
        }
    }

    if ($Shape.HasTextFrame -eq -1 -and $Shape.TextFrame.HasText -eq -1) {
        Set-MinimumRunSize -TextRange $Shape.TextFrame.TextRange -Minimum $Minimum
    }
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)

    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            Set-ShapeMinimumFont -Shape $shape -Minimum $MinimumPt
        }
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    }
    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }
    $presentation.SaveCopyAs($OutputPath)
    Write-Output "Saved $OutputPath"
}
finally {
    if ($null -ne $presentation) {
        try {
            $presentation.Close()
        }
        catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null
    }
    try {
        $ppt.Quit()
    }
    catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
