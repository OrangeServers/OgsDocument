[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$errors = [System.Collections.Generic.List[string]]::new()

Push-Location $repoRoot
try {
    $markdownPaths = & rg --files `
        -g '*.md' `
        -g '!.agents/**' `
        -g '!.pnpm-store/**' `
        -g '!node_modules/**' `
        -g '!frontend/dist/**' `
        -g '!.deploy_notes_*.md' `
        -g '!docs/research/**'
    if ($LASTEXITCODE -ne 0) {
        throw 'rg failed while listing Markdown files'
    }
} finally {
    Pop-Location
}
$publicMarkdown = $markdownPaths | ForEach-Object {
    Get-Item -LiteralPath (Join-Path $repoRoot $_)
}

foreach ($file in $publicMarkdown) {
    $relativeFile = [System.IO.Path]::GetRelativePath($repoRoot, $file.FullName).
        Replace('\', '/')
    $content = Get-Content -LiteralPath $file.FullName -Raw

    if ($content -match '(?im)[ \t]+$') {
        $errors.Add("$relativeFile`: trailing whitespace")
    }

    if ($content -match '(?i)GPL-3\.0') {
        $errors.Add("$relativeFile`: stale GPL-3.0 reference; project license is Apache-2.0")
    }

    if ($content -match '(?i)(?:/data/install|10\.0\.1\.\d{1,3}|root@10\.)') {
        $errors.Add("$relativeFile`: possible private deployment address or path")
    }

    if ($content -match '(?i)(?:\d{3,5}\+?\s+(?:passed|tests?|用例)|passed\s*/\s*\d+\s+skipped)') {
        $errors.Add("$relativeFile`: volatile test count")
    }

    $markdownMatches = [regex]::Matches(
        $content,
        '\[[^\]]+\]\((?<target>[^)\s]+)(?:\s+"[^"]*")?\)'
    )
    $htmlMatches = [regex]::Matches(
        $content,
        '(?:href|src)="(?<target>[^"]+)"'
    )
    $targets = @($markdownMatches) + @($htmlMatches) |
        ForEach-Object { $_.Groups['target'].Value.Trim('<', '>') }
    foreach ($target in $targets) {
        if (
            $target.StartsWith('#') -or
            $target -match '^(?i:https?|mailto):' -or
            $target.StartsWith('/')
        ) {
            continue
        }

        $pathPart = [Uri]::UnescapeDataString(($target -split '#', 2)[0])
        if ([string]::IsNullOrWhiteSpace($pathPart)) {
            continue
        }
        $resolved = [System.IO.Path]::GetFullPath(
            (Join-Path $file.DirectoryName $pathPart)
        )
        if (-not $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $errors.Add("$relativeFile`: link escapes repository: $target")
            continue
        }
        if (-not (Test-Path -LiteralPath $resolved)) {
            $errors.Add("$relativeFile`: broken link: $target")
        }
    }
}

$daemonExamplePath = Join-Path $repoRoot 'deploy/daemon.json.example'
try {
    $daemonExample = Get-Content -LiteralPath $daemonExamplePath -Raw |
        ConvertFrom-Json
    $allowedDaemonKeys = @(
        'registry-mirrors',
        'max-concurrent-downloads',
        'log-driver',
        'log-opts'
    )
    foreach ($property in $daemonExample.PSObject.Properties.Name) {
        if ($property -notin $allowedDaemonKeys) {
            $errors.Add(
                "deploy/daemon.json.example: unsupported example key: $property"
            )
        }
    }
} catch {
    $errors.Add('deploy/daemon.json.example: invalid JSON')
}

$launcherEntrypoints = @(
    'README.md',
    'README.zh-CN.md',
    'website/guide/deployment.md',
    'website/guide/getting-started.md',
    'website/zh/guide/deployment.md',
    'website/zh/guide/getting-started.md',
    'website/.vitepress/theme/installCommands.ts'
)
foreach ($relativePath in $launcherEntrypoints) {
    $content = Get-Content -LiteralPath (Join-Path $repoRoot $relativePath) -Raw
    if ($content -notmatch 'bootstrap-compose\.sh') {
        $errors.Add("$relativePath`: missing versioned launcher entrypoint")
    }
    if ($content -match 'git clone[^\r\n]*OrangeServer') {
        $errors.Add("$relativePath`: stale source-build primary entrypoint")
    }
    if ($content -notmatch 'set -o pipefail') {
        $errors.Add("$relativePath`: launcher pipeline can hide curl failures")
    }
    $releaseVersion = [regex]::Match(
        $content,
        'releases/download/(?<version>v\d+\.\d+\.\d+)/bootstrap-compose\.sh'
    ).Groups['version'].Value
    $argumentVersion = [regex]::Match(
        $content,
        '--version\s+(?<version>v\d+\.\d+\.\d+)'
    ).Groups['version'].Value
    if (
        [string]::IsNullOrWhiteSpace($releaseVersion) -or
        $releaseVersion -ne $argumentVersion
    ) {
        $errors.Add("$relativePath`: launcher URL and --version do not match")
    }
    $chinaVersion = [regex]::Match(
        $content,
        'gitee\.com/orangeservers/OrangeServer/raw/(?<version>v\d+\.\d+\.\d+)/ops/bootstrap-compose-cn\.sh'
    ).Groups['version'].Value
    $chinaArgumentVersion = [regex]::Match(
        $content,
        'bootstrap-compose-cn\.sh[\s\S]{0,200}?--version\s+(?<version>v\d+\.\d+\.\d+)'
    ).Groups['version'].Value
    if (
        [string]::IsNullOrWhiteSpace($chinaVersion) -or
        $chinaVersion -ne $chinaArgumentVersion
    ) {
        $errors.Add("$relativePath`: China launcher URL and --version do not match")
    }
}

$homepageInstallComponents = @(
    'website/.vitepress/theme/components/HomeCta.vue',
    'website/.vitepress/theme/components/HeroExtras.vue'
)
foreach ($relativePath in $homepageInstallComponents) {
    $content = Get-Content -LiteralPath (Join-Path $repoRoot $relativePath) -Raw
    if ($content -notmatch "from '../installCommands'") {
        $errors.Add("$relativePath`: must use the shared versioned launcher commands")
    }
}

$upgradeContent = Get-Content -LiteralPath (
    Join-Path $repoRoot 'docs/operations/UPGRADE.md'
) -Raw
if ($upgradeContent -match '127\.0\.0\.1:28000/local/health') {
    $errors.Add(
        'docs/operations/UPGRADE.md: Compose health check uses unpublished backend port'
    )
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object {
        Write-Host $_ -ForegroundColor Red
    }
    exit 1
}

Write-Host "Documentation checks passed ($($publicMarkdown.Count) Markdown files)."
