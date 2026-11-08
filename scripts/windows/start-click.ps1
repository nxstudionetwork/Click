# Click - one-click local start for Windows (DEVELOPMENT).
# Safe to run every time: installs only what changed, never deletes data.
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root

function Say($text, $color = 'Cyan') { Write-Host ''; Write-Host "==> $text" -ForegroundColor $color }
function Fail($text) { Write-Host ''; Write-Host $text -ForegroundColor Red; Read-Host 'Press Enter to close'; exit 1 }

# ---------------------------------------------------------------- 1. Required programs
Say 'Checking required programs'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js is not installed.`nInstall 'Node.js 22 LTS' from https://nodejs.org (keep the default options), then double-click START-CLICK.bat again." }
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py -or ($py.Source -like '*WindowsApps*')) { Fail "Python is not installed.`nInstall Python 3.12 or newer from https://www.python.org/downloads/`nIMPORTANT: on the first installer screen tick 'Add python.exe to PATH'. Then double-click START-CLICK.bat again." }
$psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psql) {
  $psql = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $psql) { Fail "PostgreSQL is not installed.`nInstall PostgreSQL 16 from https://www.postgresql.org/download/windows/ (keep default options, port 5432).`nWrite down the password you choose for the 'postgres' user. Then double-click START-CLICK.bat again." }
Write-Host "Node $(node --version), $(python --version), PostgreSQL found."

# ---------------------------------------------------------------- 2. App packages
$lock = Get-FileHash package-lock.json
$stamp = 'node_modules\.click-lock-hash'
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $lock.Hash) {
  Say 'Installing app packages (first time takes a few minutes)'
  npm install
  if ($LASTEXITCODE -ne 0) { Fail 'npm install failed. Check your internet connection and try again.' }
  Set-Content $stamp $lock.Hash
}

# ---------------------------------------------------------------- 3. Backend packages
Set-Location (Join-Path $Root 'backend')
if (-not (Test-Path '.venv\Scripts\python.exe')) { Say 'Creating Python environment'; python -m venv .venv }
$venvPy = Join-Path (Get-Location) '.venv\Scripts\python.exe'
$req = (Get-FileHash requirements.txt).Hash + (Get-FileHash requirements-dev.txt).Hash
$reqStamp = '.venv\.click-req-hash'
if (-not (Test-Path $reqStamp) -or (Get-Content $reqStamp) -ne $req) {
  Say 'Installing backend packages'
  & $venvPy -m pip install --upgrade pip --quiet
  & $venvPy -m pip install -r requirements-dev.txt
  if ($LASTEXITCODE -ne 0) { Fail 'Installing backend packages failed. Check your internet connection and try again.' }
  Set-Content $reqStamp $req
}
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Write-Host 'Created backend\.env (development settings).' }

# ---------------------------------------------------------------- 4. Database (created once)
# (Windows PowerShell 5 treats redirected stderr as an error under 'Stop', so relax it for this probe.)
$ErrorActionPreference = 'Continue'
$dbOk = & $venvPy -c "import psycopg; psycopg.connect('postgresql://click:click@localhost:5432/click', connect_timeout=5).close(); print('ok')" 2>$null
$ErrorActionPreference = 'Stop'
if ($dbOk -ne 'ok') {
  Say 'Creating the Click database (one time)' 'Yellow'
  Write-Host "Enter the password you chose for the 'postgres' user when you installed PostgreSQL." -ForegroundColor Yellow
  $sql = Join-Path $env:TEMP 'click-create-db.sql'
  @'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'click') THEN
    CREATE ROLE click LOGIN PASSWORD 'click' CREATEDB;
  END IF;
END $$;
SELECT 'CREATE DATABASE click OWNER click' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'click')\gexec
'@ | Set-Content -Encoding ASCII $sql
  & $psql -U postgres -h localhost -p 5432 -v ON_ERROR_STOP=1 -f $sql
  if ($LASTEXITCODE -ne 0) { Fail "Could not create the database. Check the 'postgres' password and that PostgreSQL is running (Windows Services: postgresql-x64-16)." }
}

Say 'Updating database and development data'
& $venvPy manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { Fail 'Database update failed (see the message above).' }
& $venvPy manage.py seed_dev_data
if ($LASTEXITCODE -ne 0) { Fail 'Loading development data failed (see the message above).' }

# ---------------------------------------------------------------- 5. Start
Say 'Starting Click' 'Green'
$backendDir = Join-Path $Root 'backend'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$backendDir'; `$host.UI.RawUI.WindowTitle = 'Click API (port 4000) - keep open'; & '$venvPy' manage.py runserver"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$Root'; `$host.UI.RawUI.WindowTitle = 'Click Customer App (port 5173) - keep open'; npm run dev:customer"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$Root'; `$host.UI.RawUI.WindowTitle = 'Click Partner App (port 5174) - keep open'; npm run dev:partner"

Write-Host 'Waiting for Click to start...'
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://localhost:5173/api/health' | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}
Start-Process 'http://localhost:5173'
Write-Host ''
Write-Host 'Click is running at http://localhost:5173' -ForegroundColor Green
Write-Host 'Click Partner is running at http://localhost:5174' -ForegroundColor Green
Write-Host 'Three windows were opened (API, Customer App and Partner App). Keep them open while you use Click; close them to stop.'
Write-Host 'Quick sign-in for testing: on the sign-in screen use "Login as Test Customer".'
