param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [double]$MinimumPt = 12
)

$ErrorActionPreference = "Stop"
$runCount = 0
$belowMinimum = 0
$nonNumeric = 0
$minimumSeen = [double]::MaxValue

function Inspect-TextRange {
    param([object]$TextRange)

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
            if ($size -gt 0) {
                $script:runCount++
                if ($size -lt $script:minimumSeen) {
                    $script:minimumSeen = $size
                }
                if ($size -lt $MinimumPt) {
                    $script:belowMinimum++
                }
            }
            else {
                $script:nonNumeric++
            }
        }
        catch {
            $script:nonNumeric++
        }
    }
}

function Inspect-Shape {
    param([object]$Shape)

    if ($Shape.Type -eq 6) {
        foreach ($child in $Shape.GroupItems) {
            Inspect-Shape -Shape $child
        }
        return
    }

    if ($Shape.HasTable -eq -1) {
        $table = $Shape.Table
        for ($row = 1; $row -le $table.Rows.Count; $row++) {
            for ($column = 1; $column -le $table.Columns.Count; $column++) {
                $cellShape = $table.Cell($row, $column).Shape
                if ($cellShape.HasTextFrame -eq -1 -and $cellShape.TextFrame.HasText -eq -1) {
                    Inspect-TextRange -TextRange $cellShape.TextFrame.TextRange
                }
            }
        }
    }

    if ($Shape.HasTextFrame -eq -1 -and $Shape.TextFrame.HasText -eq -1) {
        Inspect-TextRange -TextRange $Shape.TextFrame.TextRange
    }
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)
    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            Inspect-Shape -Shape $shape
        }
    }
    Write-Output "Slides: $($presentation.Slides.Count)"
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

Write-Output "Runs checked: $runCount"
Write-Output "Minimum font: $minimumSeen pt"
Write-Output "Runs below $MinimumPt pt: $belowMinimum"
Write-Output "Runs without numeric size: $nonNumeric"

if ($belowMinimum -gt 0) {
    exit 1
}
