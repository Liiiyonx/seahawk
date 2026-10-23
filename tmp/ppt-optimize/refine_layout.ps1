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

function Set-MetricChip {
    param(
        [object]$Slide,
        [string]$BoxName,
        [string]$TextName,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [string]$Text
    )

    $box = Get-ShapeByName -Slide $Slide -Name $BoxName
    $label = Get-ShapeByName -Slide $Slide -Name $TextName

    $box.Left = $Left
    $box.Top = $Top
    $box.Width = $Width
    $box.Height = $Height

    $label.Left = $Left + 0.05
    $label.Top = $Top + 0.03
    $label.Width = $Width - 0.1
    $label.Height = $Height - 0.06
    $label.TextFrame2.MarginLeft = 1
    $label.TextFrame2.MarginRight = 1
    $label.TextFrame2.MarginTop = 0
    $label.TextFrame2.MarginBottom = 0
    $label.TextFrame2.WordWrap = -1
    $label.TextFrame2.VerticalAnchor = 3
    $label.TextFrame2.TextRange.Text = $Text
    $label.TextFrame2.TextRange.Font.Name = "Microsoft YaHei"
    $label.TextFrame2.TextRange.Font.NameFarEast = "Microsoft YaHei"
    $label.TextFrame2.TextRange.Font.Size = 12
    $label.TextFrame2.TextRange.Font.Bold = -1
    $label.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = 0x0F2E4C
    $label.TextFrame2.TextRange.ParagraphFormat.Alignment = 2
    $label.TextFrame2.TextRange.ParagraphFormat.SpaceBefore = 0
    $label.TextFrame2.TextRange.ParagraphFormat.SpaceAfter = 0
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)
    $slide = $presentation.Slides[16]

    $chipDefinitions = @(
        @{ Box = "Rounded Rectangle 33"; Text = "TextBox 34"; Label = "分类 Precision / Recall / F1" },
        @{ Box = "Rounded Rectangle 35"; Text = "TextBox 36"; Label = "AP50 / AP50-95" },
        @{ Box = "Rounded Rectangle 37"; Text = "TextBox 38"; Label = "每千帧误报数" },
        @{ Box = "Rounded Rectangle 39"; Text = "TextBox 40"; Label = "事件级发现率" },
        @{ Box = "Rounded Rectangle 41"; Text = "TextBox 42"; Label = "确认时延" },
        @{ Box = "Rounded Rectangle 43"; Text = "TextBox 44"; Label = "天气 / 光照分层" },
        @{ Box = "Rounded Rectangle 45"; Text = "TextBox 46"; Label = "样本量 / 置信区间" }
    )

    $startLeft = 0.62
    $top = 5.56
    $chipWidth = 1.62
    $chipHeight = 0.5
    $gap = 0.075

    for ($index = 0; $index -lt $chipDefinitions.Count; $index++) {
        $definition = $chipDefinitions[$index]
        $left = $startLeft + ($index * ($chipWidth + $gap))
        Set-MetricChip `
            -Slide $slide `
            -BoxName $definition.Box `
            -TextName $definition.Text `
            -Left $left `
            -Top $top `
            -Width $chipWidth `
            -Height $chipHeight `
            -Text $definition.Label
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
