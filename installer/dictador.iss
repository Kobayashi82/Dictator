; Instalador de Dictador (Inno Setup 6). Se compila con `uv run python installer/build.py`.
; Instala para el usuario actual (sin pedir permisos de administrador), crea el icono del escritorio y del menú
; Inicio y hace que los documentos .dictador se abran con doble clic. Los modelos no van dentro: los descarga el
; asistente del programa la primera vez.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B0E3F7C-2D1A-4C8E-9B57-5E1F0A2C7D41}
AppName=Dictador
AppVersion={#AppVersion}
AppVerName=Dictador {#AppVersion}
AppPublisher=Kobayashi82
DefaultDirName={autopf}\Dictador
DefaultGroupName=Dictador
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Instalar Dictador
SetupIconFile=..\src\dictador\ui\assets\dictador.ico
UninstallDisplayIcon={app}\Dictador.exe
UninstallDisplayName=Dictador
WizardStyle=modern
WizardSizePercent=120
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
es.WelcomeLabel2=Se va a instalar Dictador, el programa que escribe lo que usted dice en voz alta.%n%nPulse «Siguiente» para continuar.
es.FinishedLabel=Dictador ya está instalado. Encontrará su icono en el escritorio.

[Tasks]
Name: "desktopicon"; Description: "Poner un icono en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\Dictador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Dictador"; Filename: "{app}\Dictador.exe"
Name: "{autodesktop}\Dictador"; Filename: "{app}\Dictador.exe"; Tasks: desktopicon

[Registry]
; Documentos .dictador (y los antiguos .dictado) se abren con Dictador.
Root: HKA; Subkey: "Software\Classes\.dictador"; ValueType: string; ValueName: ""; ValueData: "Dictador.Documento"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.dictado"; ValueType: string; ValueName: ""; ValueData: "Dictador.Documento"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Dictador.Documento"; ValueType: string; ValueName: ""; ValueData: "Documento de Dictador"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Dictador.Documento\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Dictador.exe,0"
Root: HKA; Subkey: "Software\Classes\Dictador.Documento\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Dictador.exe"" ""%1"""

[Run]
Filename: "{app}\Dictador.exe"; Description: "Abrir Dictador ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Si el corrector integrado quedó abierto, se cierra para poder borrar sus archivos.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Dictador.exe"; Flags: runhidden; RunOnceId: "CerrarDictador"
