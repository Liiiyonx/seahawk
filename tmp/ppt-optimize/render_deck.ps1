param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)
    foreach ($slide in $presentation.Slides) {
        $file = Join-Path $OutputDirectory ("slide-{0:D2}.png" -f $slide.SlideIndex)
        $slide.Export($file, "PNG", 1600, 900)
    }
    Write-Output "Rendered $($presentation.Slides.Count) slides to $OutputDirectory"
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
