/**
 * ae-mcp Startup Script for Adobe After Effects
 * Initializes the IPC communication folder and registers the After Effects session.
 *
 * ES3 Compliant.
 */

(function () {
    try {
        var tempFolder = Folder.temp;
        var ipcF = new Folder(tempFolder.fsName + "\\ae_mcp_ipc");
        if (!ipcF.exists) {
            ipcF.create();
        }

        var sessionFile = new File(ipcF.fsName + "\\ae_session.json");
        if (sessionFile.open("w")) {
            var sessionData = '{"status":"running","version":"' + app.version + '","appName":"' + app.appName + '","startedAt":"' + (new Date()).toString() + '"}';
            sessionFile.write(sessionData);
            sessionFile.close();
        }

        // Global namespace for ae-mcp
        if (typeof $.global.AEMCP === "undefined") {
            $.global.AEMCP = {
                version: "1.0.0",
                ready: true,
                initializedAt: new Date()
            };
        }

        writeLn("[ae-mcp] Bridge initialized for Antigravity AI companion.");
    } catch (e) {
        // Suppress non-fatal startup notifications
    }
})();
