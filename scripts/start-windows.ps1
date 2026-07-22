# UP Police Data Analyst - one-click setup + run (Windows PowerShell 5.1+)
# Run via Start-Windows.bat (double-click). Safe to re-run any time.
# NOTE: this file must stay pure ASCII (PowerShell 5.1 reads BOM-less files as ANSI).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Fail($msg) {
    Write-Host ""
    Write-Host "  PROBLEM: $msg" -ForegroundColor Red
    Write-Host "  Screenshot this window and share it to get help." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

function Step($msg) { Write-Host ""; Write-Host ">> $msg" -ForegroundColor Cyan }

Write-Host "=== UP Police Data Analyst - setup and run ===" -ForegroundColor Green
Write-Host "Folder: $root"

# ---------------------------------------------------------------- tools
Step "Checking required tools"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is not installed. It manages Python and packages (one-time install)." -ForegroundColor Yellow
    $ans = Read-Host "Install uv now? (Y/n)"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv installed but not found - close this window and run Start-Windows.bat again." }
    } else { Fail "uv is required. Install from https://docs.astral.sh/uv/ then re-run." }
}
Write-Host "  uv: OK ($(uv --version))"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "Node.js is not installed. Install Node 20+ (LTS) from https://nodejs.org then re-run this launcher."
}
$nodeMajor = [int]((node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) { Fail "Node.js $(node --version) is too old - install Node 20+ from https://nodejs.org" }
Write-Host "  node: OK ($(node --version))"

$frontendTool = "pnpm"
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Write-Host "pnpm is not installed - installing it with npm (one time)..." -ForegroundColor Yellow
    npm install -g pnpm
    if ($LASTEXITCODE -ne 0) { Fail "Could not install pnpm. Run 'npm install -g pnpm' in a new terminal, then re-run." }
    # a just-installed tool is often invisible to THIS session - refresh PATH from the registry
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath;$env:APPDATA\npm"
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        Write-Host "  pnpm installed but not visible in this window yet - using npm for this run." -ForegroundColor Yellow
        $frontendTool = "npm"
    }
}
if ($frontendTool -eq "pnpm") { Write-Host "  pnpm: OK ($(pnpm --version))" } else { Write-Host "  npm: OK ($(npm --version))" }

# ---------------------------------------------------------------- .env + key
Step "Checking .env and API key"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$envText = Get-Content ".env" -Raw
$hasGemini = $envText -match "(?m)^AGENT_GEMINI_API_KEY=\S+"
$hasAnthropic = $envText -match "(?m)^AGENT_ANTHROPIC_API_KEY=\S+"
if (-not ($hasGemini -or $hasAnthropic)) {
    Write-Host "A Gemini API key is needed. Free at https://aistudio.google.com/apikey (keys start with AIza)." -ForegroundColor Yellow
    $key = Read-Host "Paste your Gemini API key"
    if (-not $key) { Fail "No key entered. Get one at https://aistudio.google.com/apikey and re-run." }
    $envText = $envText -replace "(?m)^AGENT_GEMINI_API_KEY=.*$", "AGENT_GEMINI_API_KEY=$key"
    Set-Content ".env" $envText -NoNewline
    Write-Host "  Key saved to .env (kept only on this computer)."
} else { Write-Host "  API key: present" }

# ---------------------------------------------------------------- setup
Step "Installing Python packages (first run may take a few minutes)"
uv sync --extra dev
if ($LASTEXITCODE -ne 0) { Fail "'uv sync' failed - see the messages above." }

Step "Building the web interface"
Push-Location frontend
if ($frontendTool -eq "pnpm") {
    pnpm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  pnpm blocked or failed the install - falling back to npm (fresh resolution)..." -ForegroundColor Yellow
        $frontendTool = "npm"
    }
}
if ($frontendTool -eq "npm") { npm install }
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Frontend package install failed - see above." }
if ($frontendTool -eq "pnpm") { pnpm build } else { npm run build }
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Frontend build failed - see above." }
Pop-Location

Step "Preparing the database"
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { Fail "Database migration failed - see above." }
$rev = (uv run alembic current) -join " "
if ($rev -notmatch "head") { Fail "Migration did not apply (alembic current: '$rev')." }
Write-Host "  Database ready ($rev)"

# ---------------------------------------------------------------- run
Step "Starting the server on http://localhost:8001"
Write-Host ""
Write-Host "  KEEP THIS WINDOW OPEN - closing it stops the app." -ForegroundColor Yellow
Write-Host "  Your browser will open automatically when it's ready." -ForegroundColor Yellow
Write-Host ""

Start-Job -ScriptBlock {
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8001/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { Start-Process "http://localhost:8001/app/"; break }
        } catch { Start-Sleep -Seconds 2 }
    }
} | Out-Null

uv run python -m src
Write-Host ""
Write-Host "Server stopped." -ForegroundColor Yellow
Read-Host "Press Enter to close"
