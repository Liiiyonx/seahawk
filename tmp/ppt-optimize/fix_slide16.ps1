param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Get-ShapeByName {
    param(
        [object]$Slide,
        [string]$Name
    )

    foreach ($shape in $Slide.Shapes) {
        if ($shape.Name -eq $Name) {
            return $shape
        }
    }
    throw "Shape '$Name' was not found on slide $($Slide.SlideIndex)"
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)
    $slide = $presentation.Slides[16]

    $placements = @(
        @{ Box = "Rounded Rectangle 41"; Text = "TextBox 42"; Left = 0.62 },
        @{ Box = "Rounded Rectangle 43"; Text = "TextBox 44"; Left = 3.78 },
        @{ Box = "Rounded Rectangle 45"; Text = "TextBox 46"; Left = 6.94 }
    )

    foreach ($placement in $placements) {
        $box = Get-ShapeByName -Slide $slide -Name $placement.Box
        $label = Get-ShapeByName -Slide $slide -Name $placement.Text

        # PowerPoint COM accepts positions in points.
        $box.Left = $placement.Left * 72
        $box.Top = 6.05 * 72
        $label.Left = $placement.Left * 72
        $label.Top = 6.13 * 72
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
