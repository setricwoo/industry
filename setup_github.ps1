# GitHub 上传脚本
# 用法: .\setup_github.ps1 -Username "你的用户名" -Token "你的Token"

param(
    [Parameter(Mandatory=$true)]
    [string]$Username,
    
    [Parameter(Mandatory=$true)]
    [string]$Token
)

$RepoName = "industry"

Write-Host "开始创建仓库并上传..." -ForegroundColor Green

# 1. 创建仓库
try {
    $body = @{
        name = $RepoName
        private = $false
        auto_init = $false
    } | ConvertTo-Json
    
    $headers = @{
        Authorization = "token $Token"
        Accept = "application/vnd.github.v3+json"
    }
    
    Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body
    Write-Host "✅ 仓库创建成功" -ForegroundColor Green
} catch {
    Write-Host "⚠️  仓库可能已存在，继续上传..." -ForegroundColor Yellow
}

# 2. 本地 git 操作
if (Test-Path .git) {
    Remove-Item -Recurse -Force .git
}

git init
git add index.html data.js
git commit -m "Initial commit: Cycle industry dashboard"
git remote add origin "https://github.com/$Username/$RepoName.git"
git branch -M main
git push -u origin main

Write-Host "✅ 上传完成！访问: https://github.com/$Username/$RepoName" -ForegroundColor Green
Write-Host "下一步：开启 GitHub Pages (Settings -> Pages)" -ForegroundColor Cyan
