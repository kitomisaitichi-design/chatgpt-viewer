$ErrorActionPreference='Stop'
$nativeRoot=Split-Path -Parent $PSScriptRoot
python (Join-Path $PSScriptRoot 'vendor-native.py')
if($LASTEXITCODE -ne 0){throw 'SDK verification failed'}
$nativeCompiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$nativeOutput=Join-Path $nativeRoot 'runtime/native'
& $nativeCompiler /nologo /target:winexe /platform:x64 /optimize+ /out:"$nativeOutput/NativeConnect.exe" /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Net.Http.dll /r:System.Web.Extensions.dll /r:"$nativeOutput/Microsoft.Web.WebView2.Core.dll" /r:"$nativeOutput/Microsoft.Web.WebView2.WinForms.dll" (Join-Path $nativeRoot 'integration/native-connection/NativeConnect.cs')
if($LASTEXITCODE -ne 0){throw 'Native connection build failed'}
$nativeSource=[IO.File]::ReadAllText((Join-Path $nativeRoot 'integration/native-connection/NativeConnect.cs')).Replace("`r`n","`n")
$nativeHasher=[Security.Cryptography.SHA256]::Create()
try{$nativeSourceHash=([BitConverter]::ToString($nativeHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($nativeSource)))).Replace('-','').ToLowerInvariant()}finally{$nativeHasher.Dispose()}
$nativeVersion=[regex]::Match([IO.File]::ReadAllText((Join-Path $nativeRoot 'viewer.py')),"VERSION = '([^']+)'").Groups[1].Value
@{version=$nativeVersion;sha256=(Get-FileHash (Join-Path $nativeOutput 'NativeConnect.exe') -Algorithm SHA256).Hash.ToLowerInvariant();source_sha256=$nativeSourceHash} | ConvertTo-Json | Set-Content -Encoding ASCII (Join-Path $nativeRoot 'integration/native-connection/helper.json')
