/**
 * ae-mcp Bridge Panel for Adobe After Effects
 * Provides a dockable ScriptUI interface for monitoring Antigravity AI bridge status,
 * inspecting active composition state, and managing IPC communication.
 *
 * ES3 Compliant.
 */

(function (thisObj) {
    function buildUI(container) {
        var win = (container instanceof Panel)
            ? container
            : new Window("palette", "ae-mcp Bridge", undefined, { resizeable: true });

        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.spacing = 8;
        win.margins = 12;

        // --- Header ---
        var titleGroup = win.add("group");
        titleGroup.orientation = "column";
        titleGroup.alignChildren = ["center", "center"];
        titleGroup.spacing = 2;

        var titleTxt = titleGroup.add("statictext", undefined, "ae-mcp Bridge");
        titleTxt.graphics.font = ScriptUI.newFont("Tahoma", "Bold", 14);

        var subTxt = titleGroup.add("statictext", undefined, "Antigravity AI Assistant Integration");
        subTxt.graphics.foregroundColor = win.graphics.newPen(win.graphics.PenType.SOLID_COLOR, [0.6, 0.6, 0.6, 1], 1);

        // Divider
        var div1 = win.add("panel", undefined, undefined);
        div1.alignment = "fill";

        // --- Status Panel ---
        var statusPanel = win.add("panel", undefined, "Bridge Status");
        statusPanel.orientation = "column";
        statusPanel.alignChildren = ["fill", "top"];
        statusPanel.spacing = 6;
        statusPanel.margins = 10;

        var secStatusText = statusPanel.add("statictext", undefined, "Checking permissions...");
        secStatusText.alignment = "fill";

        var ipcStatusText = statusPanel.add("statictext", undefined, "IPC Channel: %TEMP%\\ae_mcp_ipc");
        ipcStatusText.alignment = "fill";

        function checkSecurityPref() {
            try {
                var pref = app.preferences.getPrefAsLong("Main Pref Section", "Pref_SCRIPTING_FILE_NETWORK_SECURITY");
                if (pref === 1) {
                    secStatusText.text = "File & Network Access: ENABLED";
                } else {
                    secStatusText.text = "File & Network Access: DISABLED (Enable in Preferences)";
                }
            } catch (e) {
                secStatusText.text = "File & Network Access: Active";
            }
        }
        checkSecurityPref();

        // --- Composition Info ---
        var compPanel = win.add("panel", undefined, "Active Composition");
        compPanel.orientation = "column";
        compPanel.alignChildren = ["fill", "top"];
        compPanel.spacing = 6;
        compPanel.margins = 10;

        var compInfoText = compPanel.add("edittext", undefined, "Click 'Inspect Comp' to read active state...", { multiline: true, readonly: true });
        compInfoText.preferredSize.height = 70;
        compInfoText.alignment = "fill";

        var compBtnGroup = compPanel.add("group");
        compBtnGroup.orientation = "row";
        compBtnGroup.alignChildren = ["left", "center"];
        var inspectBtn = compBtnGroup.add("button", undefined, "Inspect Comp");

        inspectBtn.onClick = function () {
            var comp = app.project ? app.project.activeItem : null;
            if (!comp || !(comp instanceof CompItem)) {
                compInfoText.text = "No active composition found.\nPlease open or select a composition.";
                return;
            }

            var info = "Composition: " + comp.name + "\n";
            info += "Dimensions: " + comp.width + " x " + comp.height + " @ " + comp.frameRate + " fps\n";
            info += "Duration: " + comp.duration.toFixed(2) + "s (" + Math.round(comp.duration * comp.frameRate) + " frames)\n";
            info += "Total Layers: " + comp.numLayers + " (Selected: " + comp.selectedLayers.length + ")";
            compInfoText.text = info;
        };

        // --- Actions & Diagnostics ---
        var diagPanel = win.add("panel", undefined, "Diagnostics & Tools");
        diagPanel.orientation = "column";
        diagPanel.alignChildren = ["fill", "center"];
        diagPanel.spacing = 6;
        diagPanel.margins = 10;

        var diagBtnRow = diagPanel.add("group");
        diagBtnRow.orientation = "row";
        diagBtnRow.alignChildren = ["fill", "center"];
        diagBtnRow.spacing = 8;

        var openFolderBtn = diagBtnRow.add("button", undefined, "Open IPC Folder");
        var pingBtn = diagBtnRow.add("button", undefined, "Test IPC Ping");

        openFolderBtn.onClick = function () {
            var tempFolder = Folder.temp;
            var ipcF = new Folder(tempFolder.fsName + "\\ae_mcp_ipc");
            if (!ipcF.exists) {
                ipcF.create();
            }
            ipcF.execute();
        };

        pingBtn.onClick = function () {
            try {
                var tempFolder = Folder.temp;
                var ipcF = new Folder(tempFolder.fsName + "\\ae_mcp_ipc");
                if (!ipcF.exists) {
                    ipcF.create();
                }
                var pingFile = new File(ipcF.fsName + "\\panel_ping.txt");
                if (pingFile.open("w")) {
                    pingFile.write("ae-mcp bridge ping at " + (new Date()).toString());
                    pingFile.close();
                    alert("IPC ping successful!\nFile written to:\n" + pingFile.fsName);
                } else {
                    alert("Failed to write ping file to:\n" + pingFile.fsName);
                }
            } catch (err) {
                alert("Ping error: " + err.toString());
            }
        };

        // --- Footer ---
        var footerTxt = win.add("statictext", undefined, "ae-mcp v1.0.0 | Connected to Antigravity");
        footerTxt.alignment = "center";
        footerTxt.graphics.foregroundColor = win.graphics.newPen(win.graphics.PenType.SOLID_COLOR, [0.5, 0.5, 0.5, 1], 1);

        win.layout.layout(true);
        return win;
    }

    var aePanel = buildUI(thisObj);
    if (aePanel instanceof Window) {
        aePanel.center();
        aePanel.show();
    }
})(this);
