param(
    [Parameter(Mandatory)][ValidateSet('Encrypt','Decrypt')][string]$Mode,
    [Parameter(Mandatory)][string]$InputFile,
    [Parameter(Mandatory)][string]$KeyFile,
    [Parameter(Mandatory)][string]$OutputFile
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$privateRoot=[IO.Path]::GetFullPath((Join-Path $root '.local/assessment'))+[IO.Path]::DirectorySeparatorChar
$inputPath=(Resolve-Path -LiteralPath $InputFile).Path
$keyPath=[IO.Path]::GetFullPath($KeyFile)
$outputPath=[IO.Path]::GetFullPath($OutputFile)
foreach($path in @($inputPath,$keyPath,$outputPath)){
    if(-not $path.StartsWith($privateRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Backup/key/plaintext files must stay in private .local/assessment'}
}
if(Test-Path -LiteralPath $outputPath){throw 'Refusing to overwrite an existing backup/plaintext output'}
if((Get-Item -LiteralPath $inputPath).Length -gt 256MB){throw 'Use a streaming backup workflow for files above 256 MiB'}
$bytes=[IO.File]::ReadAllBytes($inputPath)
function Digest([byte[]]$value){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($value)).ToLowerInvariant()}
try {
    if($Mode -eq 'Encrypt'){
        if(Test-Path -LiteralPath $keyPath){throw 'Refusing to overwrite a backup key'}
        $key=[Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
        $nonce=[Security.Cryptography.RandomNumberGenerator]::GetBytes(12)
        $tag=[byte[]]::new(16)
        $cipher=[byte[]]::new($bytes.Length)
        $plainHash=Digest $bytes
        $aad=[Text.Encoding]::UTF8.GetBytes('LABSEAT-PG-BACKUP-1|'+$plainHash)
        $algorithm=[Security.Cryptography.AesGcm]::new($key,16)
        try{$algorithm.Encrypt($nonce,$bytes,$cipher,$tag,$aad)}finally{$algorithm.Dispose()}
        $header=@{format='LABSEAT-PG-BACKUP-1';algorithm='AES-256-GCM';plain_sha256=$plainHash;nonce=[Convert]::ToBase64String($nonce);tag=[Convert]::ToBase64String($tag)}
        $prefix=[Text.Encoding]::UTF8.GetBytes(($header|ConvertTo-Json -Compress)+"`n")
        $stream=[IO.File]::Open($outputPath,[IO.FileMode]::CreateNew)
        try{$stream.Write($prefix);$stream.Write($cipher)}finally{$stream.Dispose()}
        [IO.File]::WriteAllText($keyPath,[Convert]::ToBase64String($key))
    }else{
        $separator=[Array]::IndexOf($bytes,[byte]10)
        if($separator -lt 1 -or $separator -gt 4096){throw 'Invalid backup envelope'}
        $header=[Text.Encoding]::UTF8.GetString($bytes,0,$separator)|ConvertFrom-Json
        if($header.format -ne 'LABSEAT-PG-BACKUP-1' -or $header.algorithm -ne 'AES-256-GCM'){throw 'Unsupported backup envelope'}
        $key=[Convert]::FromBase64String([IO.File]::ReadAllText($keyPath).Trim())
        $nonce=[Convert]::FromBase64String($header.nonce)
        $tag=[Convert]::FromBase64String($header.tag)
        if($key.Length -ne 32 -or $nonce.Length -ne 12 -or $tag.Length -ne 16){throw 'Invalid backup encryption parameters'}
        $cipher=[byte[]]::new($bytes.Length-$separator-1)
        [Array]::Copy($bytes,$separator+1,$cipher,0,$cipher.Length)
        $plain=[byte[]]::new($cipher.Length)
        $aad=[Text.Encoding]::UTF8.GetBytes('LABSEAT-PG-BACKUP-1|'+$header.plain_sha256)
        $algorithm=[Security.Cryptography.AesGcm]::new($key,16)
        try{$algorithm.Decrypt($nonce,$cipher,$tag,$plain,$aad)}finally{$algorithm.Dispose()}
        if((Digest $plain) -ne $header.plain_sha256){throw 'Decrypted backup hash mismatch'}
        [IO.File]::WriteAllBytes($outputPath,$plain)
    }
    Write-Output "$Mode completed; output SHA-256=$(Digest ([IO.File]::ReadAllBytes($outputPath)))"
}finally{
    if($key){[Security.Cryptography.CryptographicOperations]::ZeroMemory($key)}
    if($plain){[Security.Cryptography.CryptographicOperations]::ZeroMemory($plain)}
}
