param(
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$Launcher = Join-Path $ProjectRoot "Mairon.pyw"
$IconPath = Join-Path $ProjectRoot "assets\mairon.ico"

$AppUserModelId = "OliverDuck.Mairon.Desktop.v1"

if (-not (Test-Path $Pythonw)) {
    throw "Mairon's virtual-environment pythonw.exe was not found at: $Pythonw"
}

if (-not (Test-Path $Launcher)) {
    throw "Mairon.pyw was not found at: $Launcher"
}

# ---------------------------------------------------------------------------
# Windows shell property helper
#
# A normal WScript.Shell shortcut can set target/icon/working directory, but
# it cannot set System.AppUserModel.ID. Without that property Windows sees the
# pinned shortcut and running Mairon process as two different taskbar apps.
# ---------------------------------------------------------------------------

$ShellIdentitySource = @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct PROPERTYKEY
{
    public Guid fmtid;
    public uint pid;

    public PROPERTYKEY(Guid fmtid, uint pid)
    {
        this.fmtid = fmtid;
        this.pid = pid;
    }
}

[StructLayout(LayoutKind.Explicit)]
public struct PROPVARIANT
{
    [FieldOffset(0)]
    public ushort vt;

    [FieldOffset(8)]
    public IntPtr pointerValue;

    public static PROPVARIANT FromString(string value)
    {
        PROPVARIANT pv = new PROPVARIANT();
        pv.vt = 31; // VT_LPWSTR
        pv.pointerValue = Marshal.StringToCoTaskMemUni(value);
        return pv;
    }
}

[ComImport]
[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore
{
    uint GetCount(out uint cProps);

    void GetAt(
        uint iProp,
        out PROPERTYKEY pkey
    );

    void GetValue(
        ref PROPERTYKEY key,
        out PROPVARIANT pv
    );

    void SetValue(
        ref PROPERTYKEY key,
        ref PROPVARIANT pv
    );

    void Commit();
}

public static class MaironShellIdentity
{
    private const uint GPS_READWRITE = 0x00000002;

    private static readonly Guid IID_IPropertyStore =
        new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");

    private static readonly PROPERTYKEY PKEY_AppUserModel_ID =
        new PROPERTYKEY(
            new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            5
        );

    [DllImport(
        "shell32.dll",
        CharSet = CharSet.Unicode,
        PreserveSig = true
    )]
    private static extern int SHGetPropertyStoreFromParsingName(
        string pszPath,
        IntPtr pbc,
        uint flags,
        ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)]
        out IPropertyStore ppv
    );

    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(
        ref PROPVARIANT pvar
    );

    public static void SetAppUserModelId(
        string shortcutPath,
        string appUserModelId
    )
    {
        Guid iid = IID_IPropertyStore;
        IPropertyStore store;

        int hr = SHGetPropertyStoreFromParsingName(
            shortcutPath,
            IntPtr.Zero,
            GPS_READWRITE,
            ref iid,
            out store
        );

        if (hr != 0)
        {
            Marshal.ThrowExceptionForHR(hr);
        }

        PROPVARIANT value =
            PROPVARIANT.FromString(appUserModelId);

        try
        {
            PROPERTYKEY key =
                PKEY_AppUserModel_ID;

            store.SetValue(
                ref key,
                ref value
            );

            store.Commit();
        }
        finally
        {
            PropVariantClear(
                ref value
            );

            if (store != null)
            {
                Marshal.FinalReleaseComObject(
                    store
                );
            }
        }
    }
}
"@

if (-not ("MaironShellIdentity" -as [type])) {
    Add-Type `
        -TypeDefinition $ShellIdentitySource `
        -Language CSharp
}

$Shell = New-Object -ComObject WScript.Shell

function New-MaironShortcut {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ShortcutPath
    )

    if (Test-Path $ShortcutPath) {
        Remove-Item `
            -Path $ShortcutPath `
            -Force
    }

    $Shortcut = $Shell.CreateShortcut(
        $ShortcutPath
    )

    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = "`"$Launcher`""
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "Mairon Personal AI"
    $Shortcut.WindowStyle = 1

    if (Test-Path $IconPath) {
        $Shortcut.IconLocation = "$IconPath,0"
    }
    else {
        $Shortcut.IconLocation = "$Pythonw,0"
    }

    $Shortcut.Save()

    [MaironShellIdentity]::SetAppUserModelId(
        $ShortcutPath,
        $AppUserModelId
    )
}

$StartMenuDirectory = Join-Path `
    $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs"

$StartMenuShortcut = Join-Path `
    $StartMenuDirectory `
    "Mairon.lnk"

New-MaironShortcut `
    -ShortcutPath $StartMenuShortcut

Write-Host ""
Write-Host "Created Start Menu shortcut:"
Write-Host "  $StartMenuShortcut"
Write-Host "  AppUserModelID: $AppUserModelId"

if (-not $NoDesktopShortcut) {
    $DesktopDirectory = [Environment]::GetFolderPath(
        "Desktop"
    )

    $DesktopShortcut = Join-Path `
        $DesktopDirectory `
        "Mairon.lnk"

    New-MaironShortcut `
        -ShortcutPath $DesktopShortcut

    Write-Host ""
    Write-Host "Created Desktop shortcut:"
    Write-Host "  $DesktopShortcut"
    Write-Host "  AppUserModelID: $AppUserModelId"
}

Write-Host ""
Write-Host "Mairon's shortcut identity now matches the running Mairon process."
Write-Host ""
Write-Host "IMPORTANT: old taskbar pins contain a cached copy of the previous shortcut."
Write-Host "Unpin every existing Mairon/Python Mairon icon from the taskbar, then:"
Write-Host "  1. Open Start"
Write-Host "  2. Search for Mairon"
Write-Host "  3. Right-click the NEW Mairon shortcut"
Write-Host "  4. Choose Pin to taskbar"
Write-Host ""
Write-Host "Mairon is also single-instance now: a second launch restores the existing"
Write-Host "window instead of creating another assistant process."
