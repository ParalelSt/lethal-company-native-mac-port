import AppKit
import Foundation

// Native launcher window: Game tab (status, play, build, updates) and Mods tab (Thunderstore browser with
// one-click install). Every action runs the Python kit ("python3 -m lcport ...") in the kit folder next to this
// app bundle; long-running output streams into the log pane.

final class Launcher: NSObject, NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate {
    let kit: URL
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LethalCompanyMac")
    var window: NSWindow!
    var log: NSTextView!
    var spinner: NSProgressIndicator!
    var statusGame = NSTextField(labelWithString: ""), statusSteam = NSTextField(labelWithString: ""), statusUnity = NSTextField(labelWithString: ""), statusLauncher = NSTextField(labelWithString: "")
    var profiles = NSPopUpButton(), profilesGame = NSPopUpButton(), importField = NSTextField()
    var search = NSSearchField(), installedOnly = NSButton(checkboxWithTitle: "Installed only", target: nil, action: nil)
    var table: NSTableView!, detail = NSTextField(wrappingLabelWithString: ""), installButton: NSButton!, removeButton: NSButton!
    var buttons: [NSButton] = []
    var process: Process?
    var results: [[String: Any]] = [], installed: [String: String] = [:], audit: [String: [String: Any]] = [:]
    var searchTimer: Timer?

    override init() { kit = Bundle.main.bundleURL.deletingLastPathComponent(); super.init() }

    func applicationDidFinishLaunching(_ n: Notification) {
        buildWindow(); refreshStatus()
        let icns = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Lethal Company.app/Contents/Resources/PlayerIcon.icns")
        if let img = NSImage(contentsOf: icns) { NSApp.applicationIconImage = img }
        Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refreshStatus() }
        NSApp.activate(ignoringOtherApps: true)
        reloadInstalled { self.doSearch() }
        // testing aid: LC_SNAPSHOT=/path.png renders the window to a file after the mod list has loaded
        if let path = ProcessInfo.processInfo.environment["LC_SNAPSHOT"] {
            if ProcessInfo.processInfo.environment["LC_SNAPSHOT_TAB"] == "mods", let tv = window.contentView?.subviews.compactMap({ $0 as? NSTabView }).first { tv.selectTabViewItem(at: 1) }
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { self.snapshot(to: path); NSApp.terminate(nil) }
        }
    }
    func snapshot(to path: String) {
        guard let cg = CGWindowListCreateImage(.null, .optionIncludingWindow, CGWindowID(window.windowNumber), [.boundsIgnoreFraming, .bestResolution]) else { return }
        let rep = NSBitmapImageRep(cgImage: cg)
        if let png = rep.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path)) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // MARK: UI helpers
    func label(_ s: String, size: CGFloat = 12, color: NSColor = .secondaryLabelColor, bold: Bool = false) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: s); l.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size); l.textColor = color; l.isSelectable = false; return l
    }
    func button(_ title: String, _ sel: Selector, prominent: Bool = false) -> NSButton {
        let b = NSButton(title: title, target: self, action: sel); b.bezelStyle = .rounded; if prominent { b.keyEquivalent = "\r" }; buttons.append(b); return b
    }
    func row(_ b: NSView, _ help: String) -> NSStackView {
        let h = label(help); h.preferredMaxLayoutWidth = 760
        let v = NSStackView(views: [b, h]); v.orientation = .vertical; v.alignment = .leading; v.spacing = 3; return v
    }
    func box(_ title: String, _ views: [NSView]) -> NSStackView {
        let sep = NSBox(); sep.boxType = .separator; sep.translatesAutoresizingMaskIntoConstraints = false
        let st = NSStackView(views: [label(title.uppercased(), size: 11, color: .tertiaryLabelColor, bold: true)] + views + [sep]); st.orientation = .vertical; st.alignment = .leading; st.spacing = 10
        st.setCustomSpacing(4, after: st.arrangedSubviews[0])
        sep.widthAnchor.constraint(equalTo: st.widthAnchor).isActive = true
        return st
    }
    func hstack(_ views: [NSView], spacing: CGFloat = 8) -> NSStackView { let s = NSStackView(views: views); s.spacing = spacing; return s }

    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 960, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Lethal Company for macOS"; window.center(); window.minSize = NSSize(width: 900, height: 700)

        // ---- Game tab
        for s in [statusGame, statusSteam, statusUnity, statusLauncher] { s.font = .systemFont(ofSize: 12) }
        let status = box("Status", [statusLauncher, statusGame, statusUnity, statusSteam])
        let play = row(button("Play", #selector(play), prominent: true), "Starts the native game. Steam is started for you if needed; stay signed in to the account that owns the game.")
        profilesGame.target = self; profilesGame.action = #selector(profileChangedGame)
        let modRow = hstack([button("Play with mods", #selector(playModded)), label("Profile:", color: .labelColor), profilesGame])
        let playModded = row(modRow, "Launches through BepInEx with the selected mod profile (manage profiles in the Mods tab).")
        let build = row(button("Build / Update game…", #selector(build)), "Pick your \"Lethal Company\" folder from a Windows Steam install (Steam > Manage > Browse local files). The launcher checks Steam ownership, extracts the game, replaces the Windows-only parts, compiles the shaders for Metal and installs the app. About an hour the first time, much less afterwards. Run it again whenever the game updates.")
        let actions = box("Game", [play, playModded, build])
        let upd = hstack([button("Check for game update", #selector(checkGame)), button("Check for launcher update", #selector(checkLauncher)), button("How it works", #selector(howItWorks)), NSView(), button("Quit", #selector(quit))])
        let updates = box("Updates", [upd])
        let gameTab = NSStackView(views: [status, actions, updates]); gameTab.orientation = .vertical; gameTab.alignment = .leading; gameTab.spacing = 14
        gameTab.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        gameTab.translatesAutoresizingMaskIntoConstraints = true; gameTab.autoresizingMask = [.width, .height]; gameTab.detachesHiddenViews = true
        for b in [status, actions, updates] { b.widthAnchor.constraint(equalTo: gameTab.widthAnchor, constant: -24).isActive = true }

        // ---- Mods tab
        profiles.target = self; profiles.action = #selector(profileChanged)
        importField.placeholderString = "Paste a Thunderstore / r2modman profile code"; importField.translatesAutoresizingMaskIntoConstraints = false
        importField.widthAnchor.constraint(equalToConstant: 320).isActive = true
        let profRow = hstack([label("Profile:", color: .labelColor), profiles, button("New…", #selector(newProfile)), button("Open folder", #selector(openProfile)), NSView(), importField, button("Import code", #selector(importCode))])
        search.placeholderString = "Search Thunderstore mods"; search.delegate = self; search.translatesAutoresizingMaskIntoConstraints = false; search.widthAnchor.constraint(equalToConstant: 320).isActive = true
        installedOnly.target = self; installedOnly.action = #selector(doSearch)
        let searchRow = hstack([search, installedOnly, NSView(), button("Audit profile", #selector(auditProfile)), button("Update all mods", #selector(updateMods))])

        table = NSTableView(); table.dataSource = self; table.delegate = self; table.rowHeight = 22; table.usesAlternatingRowBackgroundColors = true
        table.doubleAction = #selector(toggleSelected); table.target = self; table.allowsMultipleSelection = false
        for (id, title, w) in [("status", "Status", 120), ("name", "Mod", 250), ("version", "Version", 70), ("downloads", "Downloads", 90), ("desc", "Description", 380)] {
            let c = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id)); c.title = title; c.width = CGFloat(w); c.minWidth = 50; table.addTableColumn(c)
        }
        let tscroll = NSScrollView(); tscroll.documentView = table; tscroll.hasVerticalScroller = true; tscroll.borderType = .bezelBorder; tscroll.translatesAutoresizingMaskIntoConstraints = false
        tscroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 300).isActive = true
        installButton = button("Install", #selector(installSelected), prominent: false); removeButton = button("Remove", #selector(removeSelected))
        detail.font = .systemFont(ofSize: 12); detail.textColor = .secondaryLabelColor; detail.preferredMaxLayoutWidth = 700
        let actRow = hstack([installButton, removeButton, detail])
        let legend = label("Status: ✓ works on Mac · ◐ visuals auto-fixed at runtime · ✗ needs porting work · (blank) not audited yet. Install downloads the mod and its dependencies from Thunderstore straight into the selected profile.")
        let modsTab = NSStackView(views: [profRow, searchRow, tscroll, actRow, legend]); modsTab.orientation = .vertical; modsTab.alignment = .leading; modsTab.spacing = 8
        modsTab.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        modsTab.translatesAutoresizingMaskIntoConstraints = true; modsTab.autoresizingMask = [.width, .height]
        for v in [profRow, searchRow, tscroll, actRow] { v.widthAnchor.constraint(equalTo: modsTab.widthAnchor, constant: -24).isActive = true }
        legend.widthAnchor.constraint(equalTo: modsTab.widthAnchor, constant: -24).isActive = true

        let tabs = NSTabView(); tabs.translatesAutoresizingMaskIntoConstraints = false
        tabs.heightAnchor.constraint(greaterThanOrEqualToConstant: 470).isActive = true
        let t1 = NSTabViewItem(identifier: "game"); t1.label = "Game"; t1.view = gameTab
        let t2 = NSTabViewItem(identifier: "mods"); t2.label = "Mods"; t2.view = modsTab
        tabs.addTabViewItem(t1); tabs.addTabViewItem(t2)

        // ---- shared log
        log = NSTextView(); log.isEditable = false; log.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular); log.backgroundColor = .textBackgroundColor
        log.isVerticallyResizable = true; log.isHorizontallyResizable = false; log.autoresizingMask = [.width]; log.textContainer?.widthTracksTextView = true
        let scroll = NSScrollView(); scroll.documentView = log; scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder; scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.heightAnchor.constraint(equalToConstant: 170).isActive = true
        spinner = NSProgressIndicator(); spinner.style = .spinning; spinner.controlSize = .small; spinner.isDisplayedWhenStopped = false
        let logHeader = hstack([label("Log", color: .labelColor, bold: true), spinner, NSView(), button("Clear", #selector(clearLog))])
        let title = label("Lethal Company for macOS", size: 20, color: .labelColor, bold: true)
        let sub = label("Native Apple-silicon build made from your own Steam copy. No Wine. Online play, voice and mods work.")

        let root = NSStackView(views: [title, sub, tabs, logHeader, scroll]); root.orientation = .vertical; root.alignment = .leading; root.spacing = 8
        root.edgeInsets = NSEdgeInsets(top: 16, left: 18, bottom: 14, right: 18); root.translatesAutoresizingMaskIntoConstraints = false
        for v in [tabs, logHeader, scroll] as [NSView] { v.widthAnchor.constraint(equalTo: root.widthAnchor, constant: -36).isActive = true }
        tabs.setContentHuggingPriority(.defaultLow, for: .vertical)
        window.contentView = root
        window.makeKeyAndOrderFront(nil)
        appendLog("Kit folder: \(kit.path)\n")
        updateSelectionButtons()
    }

    // MARK: status
    func refreshStatus() {
        let app = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Lethal Company.app")
        var game = "Game: not built yet. Click Build / Update game."
        if let data = try? Data(contentsOf: support.appendingPathComponent("state.json")), let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any], FileManager.default.fileExists(atPath: app.path) {
            game = "Game: built \(j["built"] as? String ?? "?") with Unity \(j["unity"] as? String ?? "?"), installed in ~/Applications"
        } else if FileManager.default.fileExists(atPath: app.path) { game = "Game: installed in ~/Applications" }
        statusGame.stringValue = game
        statusSteam.stringValue = "Steam: " + (isRunning("steam_osx") ? "running" : "not running (started automatically when you play or build)")
        let editors = (try? FileManager.default.contentsOfDirectory(atPath: "/Applications/Unity/Hub/Editor")) ?? []
        let have = editors.filter { $0.hasPrefix("2022.3") }
        statusUnity.stringValue = "Unity: " + (have.isEmpty ? (FileManager.default.fileExists(atPath: "/Applications/Unity Hub.app") ? "Hub installed; the editor is downloaded during the first build" : "Unity Hub missing. Install it from unity.com and sign in once.") : "editor installed (\(have.joined(separator: ", ")))")
        statusLauncher.stringValue = "Launcher: version \(version())"
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: support.appendingPathComponent("profiles").path)) ?? []).filter { !$0.hasPrefix(".") && !$0.hasSuffix(".txt") }.sorted()
        let current = profiles.titleOfSelectedItem
        for pop in [profiles, profilesGame] where Set(names.isEmpty ? ["Default"] : names) != Set(pop.itemTitles) {
            pop.removeAllItems(); pop.addItems(withTitles: names.isEmpty ? ["Default"] : names)
            if let c = current, names.contains(c) { pop.selectItem(withTitle: c) }
        }
    }
    func version() -> String {
        if let s = try? String(contentsOf: kit.appendingPathComponent("lcport/__init__.py")), let r = s.range(of: "__version__ = \"") { return String(s[r.upperBound...].prefix(while: { $0 != "\"" })) }
        return "?"
    }
    func isRunning(_ name: String) -> Bool {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep"); p.arguments = ["-f", name]; p.standardOutput = FileHandle.nullDevice
        try? p.run(); p.waitUntilExit(); return p.terminationStatus == 0
    }

    // MARK: running the kit
    func makeProcess(_ args: [String]) -> Process {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/env"); p.arguments = ["python3", "-m", "lcport"] + args; p.currentDirectoryURL = kit
        var env = ProcessInfo.processInfo.environment; env["PATH"] = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:" + (env["PATH"] ?? ""); env["PYTHONUNBUFFERED"] = "1"; p.environment = env
        return p
    }
    func run(_ args: [String], then: (() -> Void)? = nil) {
        if process != nil { appendLog("(busy: wait for the current task to finish)\n"); return }
        let p = makeProcess(args); let pipe = Pipe(); p.standardOutput = pipe; p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { h in
            let d = h.availableData; if d.isEmpty { return }
            if let s = String(data: d, encoding: .utf8) { DispatchQueue.main.async { self.appendLog(s) } }
        }
        p.terminationHandler = { pr in
            DispatchQueue.main.async {
                pipe.fileHandleForReading.readabilityHandler = nil
                self.appendLog(pr.terminationStatus == 0 ? "\n" : "\n(exited with code \(pr.terminationStatus))\n")
                self.process = nil; self.setBusy(false); self.refreshStatus(); then?()
            }
        }
        appendLog("\n$ lcport " + args.joined(separator: " ") + "\n")
        do { try p.run(); process = p; setBusy(true) } catch { appendLog("could not start: \(error)\n") }
    }
    /// Quick JSON query (search, installed list) off the main thread.
    func kitJSON(_ args: [String], _ completion: @escaping (Any?) -> Void) {
        DispatchQueue.global().async {
            let p = self.makeProcess(args); let out = Pipe(); p.standardOutput = out; p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { DispatchQueue.main.async { completion(nil) }; return }
            let data = out.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
            let obj = try? JSONSerialization.jsonObject(with: data)
            DispatchQueue.main.async { completion(obj) }
        }
    }
    func setBusy(_ b: Bool) { b ? spinner.startAnimation(nil) : spinner.stopAnimation(nil); for x in buttons where x.title != "Clear" { x.isEnabled = !b }; if !b { updateSelectionButtons() } }
    func appendLog(_ s: String) {
        log.textStorage?.append(NSAttributedString(string: s, attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: NSColor.labelColor]))
        log.scrollToEndOfDocument(nil)
    }
    var profile: String { profiles.titleOfSelectedItem ?? "Default" }

    // MARK: Game actions
    @objc func play() { run(["play"]) }
    @objc func playModded() { run(["play-modded", profile]) }
    @objc func build() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.message = "Choose your \"Lethal Company\" folder (copied from a Windows Steam install: Steam > Lethal Company > Manage > Browse local files)"; panel.prompt = "Build"
        if panel.runModal() == .OK, let url = panel.url {
            if !FileManager.default.fileExists(atPath: url.appendingPathComponent("Lethal Company.exe").path) {
                let a = NSAlert(); a.messageText = "That folder is not a Lethal Company install"; a.informativeText = "It must contain \"Lethal Company.exe\" and \"Lethal Company_Data\"."; a.runModal(); return
            }
            run(["build", url.path])
        }
    }
    @objc func checkGame() { run(["check-update"]) }
    @objc func checkLauncher() { run(["self-update"]) }
    @objc func clearLog() { log.string = "" }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func howItWorks() {
        let a = NSAlert(); a.messageText = "How it works"
        a.informativeText = """
        1. Steam confirms that the signed-in account owns Lethal Company.
        2. Your Windows copy is extracted into a Unity project (scenes, assets, code).
        3. Windows-only parts are swapped for Mac ones: Unity packages from Unity's registry, a Steamworks compatibility layer, voice and Opus audio plugins, the Discord SDK, and replacement screen effects.
        4. Unity compiles every shader for Metal and builds a native Apple-silicon app.
        5. The game's original code assemblies go back into the app, so mods see exactly the code they were written for.
        6. The app is installed in ~/Applications with the game's icon, plus "Lethal Company Modded".

        Nothing from the game is downloaded or shared; everything is built on this Mac from your own copy.
        Online play uses the same Steam lobbies as the Windows version. Keep Steam running while you play.
        """
        a.runModal()
    }

    // MARK: Mods
    @objc func profileChanged() { profilesGame.selectItem(withTitle: profile); reloadInstalled { self.table.reloadData(); self.updateSelectionButtons() } }
    @objc func profileChangedGame() { if let t = profilesGame.titleOfSelectedItem { profiles.selectItem(withTitle: t) }; profileChanged() }
    func reloadInstalled(_ done: (() -> Void)? = nil) {
        kitJSON(["mods", "json-installed", profile]) { obj in
            if let d = obj as? [String: Any] { self.installed = d["installed"] as? [String: String] ?? [:]; self.audit = d["audit"] as? [String: [String: Any]] ?? [:] }
            done?()
        }
    }
    func controlTextDidChange(_ n: Notification) {
        searchTimer?.invalidate(); searchTimer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: false) { _ in self.doSearch() }
    }
    @objc func doSearch() {
        let q = search.stringValue
        kitJSON(["mods", "json-search", q]) { obj in
            var list = (obj as? [[String: Any]]) ?? []
            if self.installedOnly.state == .on { list = list.filter { self.installed[$0["full_name"] as? String ?? ""] != nil } }
            self.results = list; self.table.reloadData(); self.updateSelectionButtons()
        }
    }
    func numberOfRows(in tableView: NSTableView) -> Int { results.count }
    func tableView(_ tv: NSTableView, objectValueFor col: NSTableColumn?, row: Int) -> Any? {
        let r = results[row]; let full = r["full_name"] as? String ?? ""
        switch col?.identifier.rawValue {
        case "status":
            guard let v = installed[full] else { return "" }
            let g = audit[full]?["group"] as? String
            return (g == "ok" ? "✓ " : g == "auto" ? "◐ " : g == "fix" ? "✗ " : "• ") + "installed \(v)"
        case "name": return "\(r["name"] as? String ?? "")  by \(r["owner"] as? String ?? "")"
        case "version": return r["version"] as? String ?? ""
        case "downloads": let n = r["downloads"] as? Int ?? 0; return n >= 1_000_000 ? String(format: "%.1fM", Double(n) / 1e6) : n >= 1000 ? String(format: "%.0fk", Double(n) / 1e3) : "\(n)"
        default: return r["description"] as? String ?? ""
        }
    }
    func tableViewSelectionDidChange(_ n: Notification) { updateSelectionButtons() }
    func updateSelectionButtons() {
        let row = table?.selectedRow ?? -1
        guard row >= 0, row < results.count else { installButton?.isEnabled = false; removeButton?.isEnabled = false; detail.stringValue = "Select a mod. Double-click installs or removes it."; return }
        let r = results[row]; let full = r["full_name"] as? String ?? ""; let isIn = installed[full] != nil
        installButton.isEnabled = process == nil && !isIn; removeButton.isEnabled = process == nil && isIn
        var text = "\(full) \(r["version"] as? String ?? ""): \(r["description"] as? String ?? "")"
        if let notes = audit[full]?["notes"] as? [String], !notes.isEmpty { text += "\n" + notes.joined(separator: "\n") }
        detail.stringValue = text
    }
    @objc func toggleSelected() { let row = table.selectedRow; guard row >= 0 else { return }; installed[results[row]["full_name"] as? String ?? ""] != nil ? removeSelected() : installSelected() }
    @objc func installSelected() {
        let row = table.selectedRow; guard row >= 0, let full = results[row]["full_name"] as? String else { return }
        run(["mods", "install", profile, full]) { self.reloadInstalled { self.table.reloadData(); self.updateSelectionButtons() } }
    }
    @objc func removeSelected() {
        let row = table.selectedRow; guard row >= 0, let full = results[row]["full_name"] as? String else { return }
        run(["mods", "remove", profile, full]) { self.reloadInstalled { self.table.reloadData(); self.updateSelectionButtons() } }
    }
    @objc func importCode() {
        let code = importField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if code.isEmpty { appendLog("Paste a profile code first.\n"); return }
        run(["mods", "import", profile, code]) { self.importField.stringValue = ""; self.reloadInstalled { self.doSearch() } }
    }
    @objc func auditProfile() { run(["mods", "audit", profile]) { self.reloadInstalled { self.table.reloadData() } } }
    @objc func updateMods() { run(["mods", "update", profile]) { self.reloadInstalled { self.table.reloadData() } } }
    @objc func openProfile() {
        let d = support.appendingPathComponent("profiles/\(profile)/BepInEx"); try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true); NSWorkspace.shared.open(d)
    }
    @objc func newProfile() {
        let a = NSAlert(); a.messageText = "New mod profile"; a.informativeText = "Name for the new profile:"; a.addButton(withTitle: "Create"); a.addButton(withTitle: "Cancel")
        let f = NSTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24)); a.accessoryView = f
        if a.runModal() == .alertFirstButtonReturn {
            let name = f.stringValue.replacingOccurrences(of: "/", with: "-").trimmingCharacters(in: .whitespaces); if name.isEmpty { return }
            try? FileManager.default.createDirectory(at: support.appendingPathComponent("profiles/\(name)/BepInEx"), withIntermediateDirectories: true)
            refreshStatus(); profiles.selectItem(withTitle: name); profileChanged()
        }
    }
}

let app = NSApplication.shared
let delegate = Launcher()
app.delegate = delegate
app.setActivationPolicy(.regular)
let menubar = NSMenu()
let appItem = NSMenuItem(); menubar.addItem(appItem)
let appMenu = NSMenu()
appMenu.addItem(withTitle: "About Lethal Company Port", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
appMenu.addItem(NSMenuItem.separator())
appMenu.addItem(withTitle: "Hide", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
appMenu.addItem(withTitle: "Quit Lethal Company Port", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
appItem.submenu = appMenu
let editItem = NSMenuItem(); menubar.addItem(editItem)
let editMenu = NSMenu(title: "Edit")
editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
editItem.submenu = editMenu
let winItem = NSMenuItem(); menubar.addItem(winItem)
let winMenu = NSMenu(title: "Window"); winMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m"); winMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
winItem.submenu = winMenu
app.mainMenu = menubar
app.run()
