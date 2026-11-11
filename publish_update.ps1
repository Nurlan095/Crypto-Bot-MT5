param(
    [int]$VersionCode = 251,
    [string]$VersionName = "2.51",
    [string]$Changelog = "Обновление приложения Crypto Bot"
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

# 1. Update android/app/build.gradle without BOM
$gradlePath = "d:\Projects\Nurik\android\app\build.gradle"
$gradleTxt = [System.IO.File]::ReadAllText($gradlePath, $utf8NoBom)
$gradleTxt = $gradleTxt -replace 'versionCode\s+\d+', "versionCode $VersionCode"
$gradleTxt = $gradleTxt -replace 'versionName\s+"[^"]+"', "versionName `"$VersionName`""
[System.IO.File]::WriteAllText($gradlePath, $gradleTxt, $utf8NoBom)

# 2. Build Release APK
$gradleBat = (Get-ChildItem "C:\Users\vspre\.gradle\wrapper\dists\gradle-8.11.1-bin" -Recurse -Filter "gradle.bat" | Select-Object -First 1).FullName
$env:JAVA_HOME = "C:\Java\jdk-17"
& $gradleBat -p "d:\Projects\Nurik\android" assembleRelease
if ($LASTEXITCODE -ne 0) { throw "Gradle build failed" }
Copy-Item "d:\Projects\Nurik\android\app\build\outputs\apk\release\app-release.apk" "d:\Projects\Nurik\Crypto_Bot_v2_50.apk" -Force

# 3. Update server/version.json
$verObj = @{
    version_code = $VersionCode
    version_name = $VersionName
    apk_url      = "https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk"
    changelog    = $Changelog
}
$verJson = $verObj | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText("d:\Projects\Nurik\server\version.json", $verJson, $utf8NoBom)

# 4. Upload to Timeweb Ubuntu Server (72.56.85.128)
scp -i "C:\Users\vspre\.ssh\webrelax" -o StrictHostKeyChecking=no `
    "d:\Projects\Nurik\Crypto_Bot_v2_50.apk" `
    "d:\Projects\Nurik\server\version.json" `
    "d:\Projects\Nurik\server\app.py" `
    "d:\Projects\Nurik\server\bot_engine.py" `
    "d:\Projects\Nurik\server\dashboard.html" `
    root@72.56.85.128:/opt/cryptobot/

ssh -i "C:\Users\vspre\.ssh\webrelax" -o StrictHostKeyChecking=no root@72.56.85.128 "systemctl restart cryptobot.service"
Write-Output "=== Релиз v$VersionName (#$VersionCode) успешно опубликован на https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk ==="
