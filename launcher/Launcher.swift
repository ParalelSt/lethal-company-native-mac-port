import AppKit
import Foundation

// Native launcher window styled like a web app: sidebar navigation, banner header, rounded cards, row cards for mods,
// collapsible log drawer. Every action runs the Python kit ("python3 -m lcport ...") in the kit folder next to this
// app bundle; output streams into the drawer.

// MARK: - theme
enum T {
    static let canvas = NSColor(srgbRed: 0.082, green: 0.090, blue: 0.110, alpha: 1)
    static let side   = NSColor(srgbRed: 0.106, green: 0.118, blue: 0.145, alpha: 1)
    static let card   = NSColor(srgbRed: 0.122, green: 0.133, blue: 0.161, alpha: 1)
    static let card2  = NSColor(srgbRed: 0.165, green: 0.184, blue: 0.227, alpha: 1)
    static let line   = NSColor(srgbRed: 0.169, green: 0.188, blue: 0.227, alpha: 1)
    static let text   = NSColor(srgbRed: 0.906, green: 0.914, blue: 0.933, alpha: 1)
    static let muted  = NSColor(srgbRed: 0.604, green: 0.627, blue: 0.678, alpha: 1)
    static let accent = NSColor(srgbRed: 1.000, green: 0.416, blue: 0.165, alpha: 1)
    static let ok     = NSColor(srgbRed: 0.482, green: 0.847, blue: 0.561, alpha: 1)
    static let warn   = NSColor(srgbRed: 1.000, green: 0.690, blue: 0.404, alpha: 1)
    static let bad    = NSColor(srgbRed: 1.000, green: 0.420, blue: 0.420, alpha: 1)
}

final class Card: NSView {
    init(fill: NSColor = T.card, radius: CGFloat = 12) {
        super.init(frame: .zero); wantsLayer = true; layer?.backgroundColor = fill.cgColor; layer?.cornerRadius = radius
        layer?.borderColor = T.line.cgColor; layer?.borderWidth = 1; translatesAutoresizingMaskIntoConstraints = false
    }
    required init?(coder: NSCoder) { fatalError() }
}

final class FlatButton: NSButton {
    var fill: NSColor = T.accent { didSet { refresh() } }
    var textColor: NSColor = NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1) { didSet { refresh() } }
    var padding: CGFloat = 18
    convenience init(_ title: String, fill: NSColor, text: NSColor, bold: Bool = true, target: AnyObject?, action: Selector) {
        self.init(frame: .zero); self.title = title; self.fill = fill; self.textColor = text; self.target = target; self.action = action
        isBordered = false; wantsLayer = true; layer?.cornerRadius = 8; font = bold ? .boldSystemFont(ofSize: 13) : .systemFont(ofSize: 13)
        translatesAutoresizingMaskIntoConstraints = false; heightAnchor.constraint(equalToConstant: 34).isActive = true; refresh()
    }
    func refresh() {
        layer?.backgroundColor = (isEnabled ? fill : fill.withAlphaComponent(0.4)).cgColor
        let p = NSMutableParagraphStyle(); p.alignment = .center
        attributedTitle = NSAttributedString(string: title, attributes: [.foregroundColor: isEnabled ? textColor : textColor.withAlphaComponent(0.6), .font: font!, .paragraphStyle: p])
    }
    override var isEnabled: Bool { didSet { refresh() } }
    override var intrinsicContentSize: NSSize { var s = super.intrinsicContentSize; s.width += padding * 2; return s }
}

final class NavRow: NSView {
    let label = NSTextField(labelWithString: ""); var onClick: (() -> Void)?
    var selected = false { didSet { layer?.backgroundColor = selected ? T.card2.cgColor : NSColor.clear.cgColor; label.textColor = selected ? T.text : T.muted } }
    init(_ title: String) {
        super.init(frame: .zero); wantsLayer = true; layer?.cornerRadius = 8; translatesAutoresizingMaskIntoConstraints = false
        label.stringValue = title; label.font = .systemFont(ofSize: 14, weight: .medium); label.translatesAutoresizingMaskIntoConstraints = false; addSubview(label)
        NSLayoutConstraint.activate([label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12), label.centerYAnchor.constraint(equalTo: centerYAnchor), heightAnchor.constraint(equalToConstant: 36)])
        addGestureRecognizer(NSClickGestureRecognizer(target: self, action: #selector(click))); selected = false
    }
    @objc func click() { onClick?() }
    required init?(coder: NSCoder) { fatalError() }
}

final class ModCell: NSTableCellView {
    let bg = Card(fill: T.card, radius: 10)
    let name = NSTextField(labelWithString: ""), meta = NSTextField(labelWithString: ""), desc = NSTextField(wrappingLabelWithString: ""), badge = NSTextField(labelWithString: "")
    let action = FlatButton("Install", fill: T.accent, text: NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1), target: nil, action: #selector(Launcher.cellAction(_:)))
    override init(frame: NSRect) {
        super.init(frame: frame)
        addSubview(bg)
        name.font = .systemFont(ofSize: 14, weight: .semibold); name.textColor = T.text
        meta.font = .systemFont(ofSize: 11.5); meta.textColor = T.muted
        desc.font = .systemFont(ofSize: 12); desc.textColor = T.muted; desc.maximumNumberOfLines = 2; desc.lineBreakMode = .byTruncatingTail; desc.isSelectable = false
        badge.font = .systemFont(ofSize: 11, weight: .medium); badge.textColor = T.ok; badge.alignment = .right
        for v in [name, meta, desc, badge] { v.translatesAutoresizingMaskIntoConstraints = false; bg.addSubview(v) }
        action.padding = 12; bg.addSubview(action)
        NSLayoutConstraint.activate([
            bg.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 2), bg.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -2),
            bg.topAnchor.constraint(equalTo: topAnchor, constant: 3), bg.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -3),
            name.leadingAnchor.constraint(equalTo: bg.leadingAnchor, constant: 14), name.topAnchor.constraint(equalTo: bg.topAnchor, constant: 10),
            meta.leadingAnchor.constraint(equalTo: name.trailingAnchor, constant: 8), meta.firstBaselineAnchor.constraint(equalTo: name.firstBaselineAnchor),
            desc.leadingAnchor.constraint(equalTo: name.leadingAnchor), desc.topAnchor.constraint(equalTo: name.bottomAnchor, constant: 3),
            desc.trailingAnchor.constraint(lessThanOrEqualTo: badge.leadingAnchor, constant: -12),
            action.trailingAnchor.constraint(equalTo: bg.trailingAnchor, constant: -12), action.centerYAnchor.constraint(equalTo: bg.centerYAnchor), action.widthAnchor.constraint(equalToConstant: 92),
            badge.trailingAnchor.constraint(equalTo: action.leadingAnchor, constant: -12), badge.centerYAnchor.constraint(equalTo: bg.centerYAnchor), badge.widthAnchor.constraint(lessThanOrEqualToConstant: 170),
        ])
        meta.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    }
    required init?(coder: NSCoder) { fatalError() }
}

// MARK: - launcher
final class Launcher: NSObject, NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate {
    let kit: URL
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LethalCompanyMac")
    var window: NSWindow!
    var pages: [String: NSView] = [:], navRows: [String: NavRow] = [:], current = "home"
    var heroSub = NSTextField(labelWithString: ""), statusRows: [String: (NSTextField, NSTextField)] = [:]
    var profilesHome = NSPopUpButton(), profiles = NSPopUpButton(), importField = NSTextField(), search = NSSearchField(), installedOnly = NSButton(checkboxWithTitle: "Installed only", target: nil, action: nil)
    var table: NSTableView!, modCount = NSTextField(labelWithString: "")
    var log: NSTextView!, logScroll: NSScrollView!, logHeight: NSLayoutConstraint!, drawerLine = NSTextField(labelWithString: "Ready"), drawerArrow = NSTextField(labelWithString: "▸"), spinner: NSProgressIndicator!, drawerOpen = false
    var activityLog: NSTextView!
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
        if let path = ProcessInfo.processInfo.environment["LC_SNAPSHOT"] {
            if let tab = ProcessInfo.processInfo.environment["LC_SNAPSHOT_TAB"] { show(tab) }
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { self.snapshot(to: path); NSApp.terminate(nil) }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func snapshot(to path: String) {
        guard let cg = CGWindowListCreateImage(.null, .optionIncludingWindow, CGWindowID(window.windowNumber), [.boundsIgnoreFraming, .bestResolution]) else { return }
        if let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path)) }
    }

    // MARK: helpers
    func label(_ s: String, size: CGFloat = 13, color: NSColor = T.muted, weight: NSFont.Weight = .regular, wrap: Bool = true) -> NSTextField {
        let l = wrap ? NSTextField(wrappingLabelWithString: s) : NSTextField(labelWithString: s)
        l.font = .systemFont(ofSize: size, weight: weight); l.textColor = color; l.isSelectable = false; l.translatesAutoresizingMaskIntoConstraints = false; return l
    }
    func flat(_ title: String, _ sel: Selector, primary: Bool = false) -> FlatButton {
        let b = FlatButton(title, fill: primary ? T.accent : T.card2, text: primary ? NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1) : T.text, target: self, action: sel); buttons.append(b); return b
    }
    func vstack(_ views: [NSView], spacing: CGFloat = 8, insets: NSEdgeInsets = NSEdgeInsets()) -> NSStackView {
        let s = NSStackView(views: views); s.orientation = .vertical; s.alignment = .leading; s.spacing = spacing; s.edgeInsets = insets; s.translatesAutoresizingMaskIntoConstraints = false; return s
    }
    func hstack(_ views: [NSView], spacing: CGFloat = 8) -> NSStackView { let s = NSStackView(views: views); s.spacing = spacing; s.translatesAutoresizingMaskIntoConstraints = false; return s }
    func fill(_ child: NSView, in parent: NSView, insets: NSEdgeInsets = NSEdgeInsets()) {
        parent.addSubview(child); child.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([child.leadingAnchor.constraint(equalTo: parent.leadingAnchor, constant: insets.left), child.trailingAnchor.constraint(equalTo: parent.trailingAnchor, constant: -insets.right),
                                     child.topAnchor.constraint(equalTo: parent.topAnchor, constant: insets.top), child.bottomAnchor.constraint(equalTo: parent.bottomAnchor, constant: -insets.bottom)])
    }
    func styledPopup(_ p: NSPopUpButton) { p.translatesAutoresizingMaskIntoConstraints = false; p.font = .systemFont(ofSize: 13) }

    // MARK: window
    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1040, height: 740), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = "Lethal Company for macOS"; window.titlebarAppearsTransparent = true; window.titleVisibility = .hidden
        window.appearance = NSAppearance(named: .darkAqua); window.backgroundColor = T.canvas; window.center(); window.minSize = NSSize(width: 940, height: 640)
        let root = NSView(); root.wantsLayer = true; root.layer?.backgroundColor = T.canvas.cgColor; window.contentView = root

        // sidebar
        let side = NSView(); side.wantsLayer = true; side.layer?.backgroundColor = T.side.cgColor; side.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(side)
        let logo = NSView(); logo.wantsLayer = true; logo.layer?.cornerRadius = 8; logo.translatesAutoresizingMaskIntoConstraints = false
        let grad = CAGradientLayer(); grad.colors = [T.accent.cgColor, T.warn.cgColor]; grad.startPoint = CGPoint(x: 0, y: 1); grad.endPoint = CGPoint(x: 1, y: 0); grad.cornerRadius = 8; grad.frame = CGRect(x: 0, y: 0, width: 30, height: 30)
        logo.layer?.addSublayer(grad); logo.widthAnchor.constraint(equalToConstant: 30).isActive = true; logo.heightAnchor.constraint(equalToConstant: 30).isActive = true
        let brand = hstack([logo, vstack([label("Lethal Company", size: 14, color: T.text, weight: .semibold, wrap: false), label("for macOS", size: 11, color: T.muted, wrap: false)], spacing: 0)], spacing: 10)
        var nav: [NSView] = [brand]
        for (id, title) in [("home", "Home"), ("mods", "Mods"), ("activity", "Activity")] {
            let r = NavRow(title); r.onClick = { [weak self] in self?.show(id) }; navRows[id] = r; nav.append(r)
        }
        let navStack = vstack(nav, spacing: 4, insets: NSEdgeInsets(top: 44, left: 14, bottom: 14, right: 14))
        navStack.setCustomSpacing(26, after: brand)
        for r in navRows.values { r.widthAnchor.constraint(equalTo: navStack.widthAnchor, constant: -28).isActive = true }
        side.addSubview(navStack)
        let footer = vstack([label("Launcher 0.0", size: 11, color: T.muted, wrap: false), flat("Check for launcher update", #selector(checkLauncher))], spacing: 8, insets: NSEdgeInsets(top: 0, left: 14, bottom: 16, right: 14))
        side.addSubview(footer)
        NSLayoutConstraint.activate([side.leadingAnchor.constraint(equalTo: root.leadingAnchor), side.topAnchor.constraint(equalTo: root.topAnchor), side.bottomAnchor.constraint(equalTo: root.bottomAnchor), side.widthAnchor.constraint(equalToConstant: 220),
                                     navStack.topAnchor.constraint(equalTo: side.topAnchor), navStack.leadingAnchor.constraint(equalTo: side.leadingAnchor), navStack.trailingAnchor.constraint(equalTo: side.trailingAnchor),
                                     footer.leadingAnchor.constraint(equalTo: side.leadingAnchor), footer.trailingAnchor.constraint(equalTo: side.trailingAnchor), footer.bottomAnchor.constraint(equalTo: side.bottomAnchor)])

        // main column: pages + drawer
        let main = NSView(); main.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(main)
        NSLayoutConstraint.activate([main.leadingAnchor.constraint(equalTo: side.trailingAnchor), main.trailingAnchor.constraint(equalTo: root.trailingAnchor), main.topAnchor.constraint(equalTo: root.topAnchor), main.bottomAnchor.constraint(equalTo: root.bottomAnchor)])
        let pageHost = NSView(); pageHost.translatesAutoresizingMaskIntoConstraints = false; main.addSubview(pageHost)
        let drawer = buildDrawer(); main.addSubview(drawer)
        NSLayoutConstraint.activate([pageHost.leadingAnchor.constraint(equalTo: main.leadingAnchor), pageHost.trailingAnchor.constraint(equalTo: main.trailingAnchor), pageHost.topAnchor.constraint(equalTo: main.topAnchor), pageHost.bottomAnchor.constraint(equalTo: drawer.topAnchor),
                                     drawer.leadingAnchor.constraint(equalTo: main.leadingAnchor), drawer.trailingAnchor.constraint(equalTo: main.trailingAnchor), drawer.bottomAnchor.constraint(equalTo: main.bottomAnchor)])
        pages["home"] = buildHome(); pages["mods"] = buildMods(); pages["activity"] = buildActivity()
        for (_, p) in pages { fill(p, in: pageHost); p.isHidden = true }
        show("home"); window.makeKeyAndOrderFront(nil)
    }

    func buildHome() -> NSView {
        let page = NSView(); page.translatesAutoresizingMaskIntoConstraints = false
        // banner
        let hero = NSView(); hero.wantsLayer = true; hero.translatesAutoresizingMaskIntoConstraints = false
        let g = CAGradientLayer(); g.colors = [NSColor(srgbRed: 0.36, green: 0.14, blue: 0.07, alpha: 1).cgColor, NSColor(srgbRed: 0.16, green: 0.10, blue: 0.09, alpha: 1).cgColor, T.canvas.cgColor]
        g.locations = [0, 0.6, 1]; g.startPoint = CGPoint(x: 0.2, y: 1); g.endPoint = CGPoint(x: 0.8, y: 0); hero.layer?.insertSublayer(g, at: 0)
        hero.postsFrameChangedNotifications = true
        NotificationCenter.default.addObserver(forName: NSView.frameDidChangeNotification, object: hero, queue: .main) { _ in g.frame = hero.bounds }
        let title = label("LETHAL COMPANY", size: 30, color: .white, weight: .black, wrap: false)
        heroSub = label("", size: 13, color: NSColor(white: 1, alpha: 0.75), wrap: false)
        let play = flat("▶  Play", #selector(play), primary: true); play.padding = 26
        let playMods = flat("Play with mods", #selector(playModded)); styledPopup(profilesHome); profilesHome.target = self; profilesHome.action = #selector(profileChangedHome)
        let heroBtns = hstack([play, playMods, profilesHome], spacing: 10)
        let heroStack = vstack([title, heroSub, heroBtns], spacing: 10, insets: NSEdgeInsets(top: 54, left: 32, bottom: 26, right: 32))
        heroStack.setCustomSpacing(18, after: heroSub); fill(heroStack, in: hero)
        // status card
        let status = Card(); var rows: [NSView] = [label("STATUS", size: 11, color: T.muted, weight: .semibold, wrap: false)]
        for (key, name) in [("game", "Game"), ("steam", "Steam"), ("unity", "Unity"), ("launcher", "Launcher")] {
            let k = label(name, size: 13, color: T.text, weight: .medium, wrap: false); k.widthAnchor.constraint(equalToConstant: 80).isActive = true
            let v = label("", size: 13, color: T.text, wrap: false); let hint = label("", size: 12, color: T.muted, wrap: false)
            statusRows[key] = (v, hint); rows.append(hstack([k, v, hint], spacing: 12))
        }
        let statusStack = vstack(rows, spacing: 9, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)); fill(statusStack, in: status)
        // action cards
        let buildCard = Card(); fill(vstack([label("BUILD / UPDATE GAME", size: 11, color: T.muted, weight: .semibold, wrap: false),
            label("Pick your \"Lethal Company\" folder from a Windows Steam install (Steam › Manage › Browse local files). The launcher checks Steam ownership, extracts the game, swaps the Windows-only parts, compiles the shaders for Metal and installs the app. About an hour the first time, much less afterwards. Run it again when the game updates.", size: 12.5),
            flat("Choose folder and build…", #selector(build), primary: true)], spacing: 10, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)), in: buildCard)
        let upd = Card(); fill(vstack([label("UPDATES & HELP", size: 11, color: T.muted, weight: .semibold, wrap: false),
            label("The launcher checks for a newer launcher release when it starts. Game updates are detected against Steam's public build; when one ships, copy the new Windows folder over and run Build / Update again.", size: 12.5),
            hstack([flat("Check for game update", #selector(checkGame)), flat("How it works", #selector(howItWorks)), flat("Quit", #selector(quit))])], spacing: 10, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)), in: upd)
        let grid = hstack([buildCard, upd], spacing: 14); grid.distribution = .fillEqually
        let body = vstack([status, grid], spacing: 14, insets: NSEdgeInsets(top: 18, left: 28, bottom: 20, right: 28))
        status.widthAnchor.constraint(equalTo: body.widthAnchor, constant: -56).isActive = true; grid.widthAnchor.constraint(equalTo: body.widthAnchor, constant: -56).isActive = true
        let scroll = NSScrollView(); scroll.drawsBackground = false; scroll.hasVerticalScroller = true; scroll.translatesAutoresizingMaskIntoConstraints = false
        let content = vstack([hero, body], spacing: 0); content.alignment = .leading
        hero.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true; body.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        let flipped = FlippedView(); flipped.translatesAutoresizingMaskIntoConstraints = false; flipped.addSubview(content)
        NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo: flipped.leadingAnchor), content.trailingAnchor.constraint(equalTo: flipped.trailingAnchor), content.topAnchor.constraint(equalTo: flipped.topAnchor), content.bottomAnchor.constraint(equalTo: flipped.bottomAnchor)])
        scroll.documentView = flipped; page.addSubview(scroll)
        NSLayoutConstraint.activate([scroll.leadingAnchor.constraint(equalTo: page.leadingAnchor), scroll.trailingAnchor.constraint(equalTo: page.trailingAnchor), scroll.topAnchor.constraint(equalTo: page.topAnchor), scroll.bottomAnchor.constraint(equalTo: page.bottomAnchor),
                                     flipped.widthAnchor.constraint(equalTo: scroll.widthAnchor)])
        return page
    }

    func buildMods() -> NSView {
        let page = NSView(); page.translatesAutoresizingMaskIntoConstraints = false
        let title = label("Mods", size: 24, color: T.text, weight: .bold, wrap: false)
        let intro = label("Browse Thunderstore and install with one click. Mods go into the selected profile; play them from Home with \"Play with mods\". ✓ works on Mac · ◐ visuals fixed automatically at runtime · ✗ needs porting work.", size: 12.5)
        styledPopup(profiles); profiles.target = self; profiles.action = #selector(profileChanged)
        importField.placeholderString = "Paste a Thunderstore / r2modman profile code"; importField.translatesAutoresizingMaskIntoConstraints = false; importField.widthAnchor.constraint(equalToConstant: 300).isActive = true; importField.font = .systemFont(ofSize: 13)
        let row1 = hstack([label("Profile", size: 13, color: T.text, weight: .medium, wrap: false), profiles, flat("New…", #selector(newProfile)), flat("Open folder", #selector(openProfile)), NSView(), importField, flat("Import code", #selector(importCode), primary: true)], spacing: 8)
        search.placeholderString = "Search mods"; search.delegate = self; search.translatesAutoresizingMaskIntoConstraints = false; search.widthAnchor.constraint(equalToConstant: 300).isActive = true; search.font = .systemFont(ofSize: 13)
        installedOnly.target = self; installedOnly.action = #selector(doSearch); installedOnly.font = .systemFont(ofSize: 13); installedOnly.contentTintColor = T.text
        modCount = label("", size: 12, color: T.muted, wrap: false)
        let row2 = hstack([search, installedOnly, modCount, NSView(), flat("Audit profile", #selector(auditProfile)), flat("Update all", #selector(updateMods))], spacing: 10)
        table = NSTableView(); table.dataSource = self; table.delegate = self; table.rowHeight = 70; table.headerView = nil; table.backgroundColor = .clear; table.selectionHighlightStyle = .none; table.intercellSpacing = NSSize(width: 0, height: 0)
        table.addTableColumn(NSTableColumn(identifier: NSUserInterfaceItemIdentifier("mod"))); table.columnAutoresizingStyle = .firstColumnOnlyAutoresizingStyle
        let tscroll = NSScrollView(); tscroll.documentView = table; tscroll.hasVerticalScroller = true; tscroll.drawsBackground = false; tscroll.translatesAutoresizingMaskIntoConstraints = false
        let stack = vstack([title, intro, row1, row2, tscroll], spacing: 12, insets: NSEdgeInsets(top: 48, left: 28, bottom: 16, right: 28))
        stack.setCustomSpacing(6, after: title); fill(stack, in: page)
        for v in [intro, row1, row2, tscroll] as [NSView] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -56).isActive = true }
        return page
    }

    func buildActivity() -> NSView {
        let page = NSView(); page.translatesAutoresizingMaskIntoConstraints = false
        let title = label("Activity", size: 24, color: T.text, weight: .bold, wrap: false)
        let intro = label("Everything the launcher does: builds, mod installs, update checks. The same output appears in the drawer at the bottom while a task runs.", size: 12.5)
        activityLog = NSTextView(); activityLog.isEditable = false; activityLog.font = NSFont.monospacedSystemFont(ofSize: 11.5, weight: .regular); activityLog.backgroundColor = T.card; activityLog.textColor = T.text
        activityLog.isVerticallyResizable = true; activityLog.isHorizontallyResizable = false; activityLog.autoresizingMask = [.width]; activityLog.textContainer?.widthTracksTextView = true; activityLog.textContainerInset = NSSize(width: 10, height: 10)
        let s = NSScrollView(); s.documentView = activityLog; s.hasVerticalScroller = true; s.drawsBackground = false; s.wantsLayer = true; s.layer?.cornerRadius = 10; s.translatesAutoresizingMaskIntoConstraints = false
        let stack = vstack([title, intro, hstack([flat("Clear", #selector(clearLog))]), s], spacing: 12, insets: NSEdgeInsets(top: 48, left: 28, bottom: 16, right: 28)); fill(stack, in: page)
        for v in [intro, s] as [NSView] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -56).isActive = true }
        return page
    }

    func buildDrawer() -> NSView {
        let d = NSView(); d.wantsLayer = true; d.layer?.backgroundColor = T.side.cgColor; d.translatesAutoresizingMaskIntoConstraints = false
        let top = NSView(); top.wantsLayer = true; top.layer?.backgroundColor = T.line.cgColor; top.translatesAutoresizingMaskIntoConstraints = false; d.addSubview(top)
        spinner = NSProgressIndicator(); spinner.style = .spinning; spinner.controlSize = .small; spinner.isDisplayedWhenStopped = false; spinner.translatesAutoresizingMaskIntoConstraints = false
        drawerArrow.font = .systemFont(ofSize: 12); drawerArrow.textColor = T.muted; drawerLine.font = NSFont.monospacedSystemFont(ofSize: 11.5, weight: .regular); drawerLine.textColor = T.muted; drawerLine.lineBreakMode = .byTruncatingTail
        let bar = hstack([drawerArrow, drawerLine, NSView(), spinner], spacing: 8); bar.edgeInsets = NSEdgeInsets(top: 0, left: 16, bottom: 0, right: 16)
        bar.heightAnchor.constraint(equalToConstant: 30).isActive = true; bar.addGestureRecognizer(NSClickGestureRecognizer(target: self, action: #selector(toggleDrawer)))
        log = NSTextView(); log.isEditable = false; log.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular); log.backgroundColor = T.canvas; log.textColor = T.text
        log.isVerticallyResizable = true; log.isHorizontallyResizable = false; log.autoresizingMask = [.width]; log.textContainer?.widthTracksTextView = true; log.textContainerInset = NSSize(width: 10, height: 6)
        logScroll = NSScrollView(); logScroll.documentView = log; logScroll.hasVerticalScroller = true; logScroll.drawsBackground = false; logScroll.translatesAutoresizingMaskIntoConstraints = false
        logHeight = logScroll.heightAnchor.constraint(equalToConstant: 0); logHeight.isActive = true
        let stack = vstack([bar, logScroll], spacing: 0); fill(stack, in: d)
        bar.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true; logScroll.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        NSLayoutConstraint.activate([top.leadingAnchor.constraint(equalTo: d.leadingAnchor), top.trailingAnchor.constraint(equalTo: d.trailingAnchor), top.topAnchor.constraint(equalTo: d.topAnchor), top.heightAnchor.constraint(equalToConstant: 1)])
        return d
    }
    @objc func toggleDrawer() { setDrawer(!drawerOpen) }
    func setDrawer(_ open: Bool) {
        drawerOpen = open; drawerArrow.stringValue = open ? "▾" : "▸"
        NSAnimationContext.runAnimationGroup { ctx in ctx.duration = 0.18; logHeight.animator().constant = open ? 220 : 0 }
    }

    func show(_ id: String) {
        current = id
        for (k, p) in pages { p.isHidden = k != id }
        for (k, r) in navRows { r.selected = k == id }
    }

    // MARK: status
    func refreshStatus() {
        let app = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Lethal Company.app")
        var gameV = "not built", gameH = "Use Build / Update game below.", gameC = T.warn
        if let data = try? Data(contentsOf: support.appendingPathComponent("state.json")), let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any], FileManager.default.fileExists(atPath: app.path) {
            gameV = "ready"; gameH = "built \(j["built"] as? String ?? "?") · Unity \(j["unity"] as? String ?? "?") · in ~/Applications"; gameC = T.ok
        } else if FileManager.default.fileExists(atPath: app.path) { gameV = "installed"; gameH = "~/Applications/Lethal Company.app"; gameC = T.ok }
        set("game", gameV, gameH, gameC)
        let steam = isRunning("steam_osx"); set("steam", steam ? "running" : "not running", steam ? "signed-in account must own the game" : "started automatically when you play or build", steam ? T.ok : T.warn)
        let editors = ((try? FileManager.default.contentsOfDirectory(atPath: "/Applications/Unity/Hub/Editor")) ?? []).filter { $0.hasPrefix("2022.3") }
        if !editors.isEmpty { set("unity", "ready", "editor \(editors.joined(separator: ", "))", T.ok) }
        else if FileManager.default.fileExists(atPath: "/Applications/Unity Hub.app") { set("unity", "hub only", "the editor is downloaded during the first build", T.warn) }
        else { set("unity", "missing", "install Unity Hub from unity.com and sign in once", T.bad) }
        set("launcher", "version \(version())", "", T.text)
        (window.contentView?.subviews.first?.subviews.compactMap { $0 as? NSStackView }.last?.arrangedSubviews.first as? NSTextField)?.stringValue = "Launcher \(version())"
        heroSub.stringValue = gameV == "ready" ? "Native build ready · \(steam ? "Steam running" : "Steam not running") · keep Steam open while you play" : "Not built yet. Use Build / Update game below."
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: support.appendingPathComponent("profiles").path)) ?? []).filter { !$0.hasPrefix(".") && !$0.hasSuffix(".txt") }.sorted()
        let current = profiles.titleOfSelectedItem
        for pop in [profiles, profilesHome] where Set(names.isEmpty ? ["Default"] : names) != Set(pop.itemTitles) {
            pop.removeAllItems(); pop.addItems(withTitles: names.isEmpty ? ["Default"] : names)
            let saved = UserDefaults.standard.string(forKey: "lc.profile")
            if let c = current, names.contains(c) { pop.selectItem(withTitle: c) }
            else if let c = saved, names.contains(c) { pop.selectItem(withTitle: c) }
            else if names.contains("Default") { pop.selectItem(withTitle: "Default") }
        }
    }
    func set(_ key: String, _ value: String, _ hint: String, _ color: NSColor) { guard let r = statusRows[key] else { return }; r.0.stringValue = value; r.0.textColor = color; r.1.stringValue = hint }
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
        var env = ProcessInfo.processInfo.environment; env["PATH"] = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:" + (env["PATH"] ?? ""); env["PYTHONUNBUFFERED"] = "1"; p.environment = env; return p
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
        do { try p.run(); process = p; setBusy(true); if !drawerOpen && current != "activity" { setDrawer(true) } } catch { appendLog("could not start: \(error)\n") }
    }
    func kitJSON(_ args: [String], _ completion: @escaping (Any?) -> Void) {
        DispatchQueue.global().async {
            let p = self.makeProcess(args); let out = Pipe(); p.standardOutput = out; p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { DispatchQueue.main.async { completion(nil) }; return }
            let data = out.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
            let obj = try? JSONSerialization.jsonObject(with: data); DispatchQueue.main.async { completion(obj) }
        }
    }
    func setBusy(_ b: Bool) { b ? spinner.startAnimation(nil) : spinner.stopAnimation(nil); for x in buttons where x.title != "Clear" && x.title != "Quit" { x.isEnabled = !b }; if !b { drawerLine.stringValue = "Done" }; table?.reloadData() }
    func appendLog(_ s: String) {
        let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: T.text]
        log.textStorage?.append(NSAttributedString(string: s, attributes: attrs)); log.scrollToEndOfDocument(nil)
        activityLog.textStorage?.append(NSAttributedString(string: s, attributes: attrs)); activityLog.scrollToEndOfDocument(nil)
        if let last = s.split(separator: "\n").last(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty }) { drawerLine.stringValue = String(last).trimmingCharacters(in: .whitespaces) }
    }
    var profile: String { profiles.titleOfSelectedItem ?? "Default" }

    // MARK: actions
    @objc func play() { run(["play"]) }
    @objc func playModded() { run(["play-modded", profile]) }
    @objc func build() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.message = "Choose your \"Lethal Company\" folder (copied from a Windows Steam install: Steam > Lethal Company > Manage > Browse local files)"; panel.prompt = "Build"
        if panel.runModal() == .OK, let url = panel.url {
            if !FileManager.default.fileExists(atPath: url.appendingPathComponent("Lethal Company.exe").path) {
                let a = NSAlert(); a.messageText = "That folder is not a Lethal Company install"; a.informativeText = "It must contain \"Lethal Company.exe\" and \"Lethal Company_Data\"."; a.runModal(); return
            }
            show("activity"); run(["build", url.path])
        }
    }
    @objc func checkGame() { run(["check-update"]) }
    @objc func checkLauncher() { run(["self-update"]) }
    @objc func clearLog() { log.string = ""; activityLog.string = "" }
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

    // MARK: mods
    @objc func profileChanged() { UserDefaults.standard.set(profile, forKey: "lc.profile"); profilesHome.selectItem(withTitle: profile); reloadInstalled { self.table.reloadData() } }
    @objc func profileChangedHome() { if let t = profilesHome.titleOfSelectedItem { profiles.selectItem(withTitle: t) }; profileChanged() }
    func reloadInstalled(_ done: (() -> Void)? = nil) {
        kitJSON(["mods", "json-installed", profile]) { obj in
            if let d = obj as? [String: Any] { self.installed = d["installed"] as? [String: String] ?? [:]; self.audit = d["audit"] as? [String: [String: Any]] ?? [:] }
            done?()
        }
    }
    func controlTextDidChange(_ n: Notification) { searchTimer?.invalidate(); searchTimer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: false) { _ in self.doSearch() } }
    @objc func doSearch() {
        kitJSON(["mods", "json-search", search.stringValue]) { obj in
            var list = (obj as? [[String: Any]]) ?? []
            if self.installedOnly.state == .on { list = list.filter { self.installed[$0["full_name"] as? String ?? ""] != nil } }
            self.results = list; self.modCount.stringValue = "\(list.count) mods"; self.table.reloadData()
        }
    }
    func numberOfRows(in tableView: NSTableView) -> Int { results.count }
    func tableView(_ tv: NSTableView, viewFor col: NSTableColumn?, row: Int) -> NSView? {
        let cell = (tv.makeView(withIdentifier: NSUserInterfaceItemIdentifier("ModCell"), owner: nil) as? ModCell) ?? { let c = ModCell(frame: .zero); c.identifier = NSUserInterfaceItemIdentifier("ModCell"); return c }()
        let r = results[row]; let full = r["full_name"] as? String ?? ""
        cell.name.stringValue = r["name"] as? String ?? ""
        let n = r["downloads"] as? Int ?? 0; let dl = n >= 1_000_000 ? String(format: "%.1fM", Double(n) / 1e6) : n >= 1000 ? String(format: "%.0fk", Double(n) / 1e3) : "\(n)"
        cell.meta.stringValue = "by \(r["owner"] as? String ?? "")  ·  \(r["version"] as? String ?? "")  ·  \(dl) downloads"
        cell.desc.stringValue = r["description"] as? String ?? ""
        if let v = installed[full] {
            let g = audit[full]?["group"] as? String
            cell.badge.stringValue = (g == "ok" ? "✓ works" : g == "auto" ? "◐ auto-fixed" : g == "fix" ? "✗ needs work" : "● installed") + " · \(v)"
            cell.badge.textColor = g == "fix" ? T.bad : g == "auto" ? T.warn : T.ok
            cell.action.title = "Remove"; cell.action.fill = T.card2; cell.action.textColor = T.text
        } else {
            cell.badge.stringValue = ""; cell.action.title = "Install"; cell.action.fill = T.accent; cell.action.textColor = NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1)
        }
        cell.action.target = self; cell.action.tag = row; cell.action.isEnabled = process == nil; cell.action.refresh()
        return cell
    }
    @objc func cellAction(_ sender: NSButton) {
        let row = sender.tag; guard row >= 0, row < results.count, let full = results[row]["full_name"] as? String else { return }
        run(["mods", installed[full] != nil ? "remove" : "install", profile, full]) { self.reloadInstalled { self.table.reloadData() } }
    }
    @objc func importCode() {
        let code = importField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if code.isEmpty { appendLog("Paste a profile code first.\n"); setDrawer(true); return }
        run(["mods", "import", profile, code]) { self.importField.stringValue = ""; self.reloadInstalled { self.doSearch() } }
    }
    @objc func auditProfile() { run(["mods", "audit", profile]) { self.reloadInstalled { self.table.reloadData() } } }
    @objc func updateMods() { run(["mods", "update", profile]) { self.reloadInstalled { self.table.reloadData() } } }
    @objc func openProfile() { let d = support.appendingPathComponent("profiles/\(profile)/BepInEx"); try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true); NSWorkspace.shared.open(d) }
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

final class FlippedView: NSView { override var isFlipped: Bool { true } }

let app = NSApplication.shared
let delegate = Launcher()
app.delegate = delegate
app.setActivationPolicy(.regular)
let menubar = NSMenu(); let appItem = NSMenuItem(); menubar.addItem(appItem); let appMenu = NSMenu()
appMenu.addItem(withTitle: "About Lethal Company Port", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
appMenu.addItem(NSMenuItem.separator()); appMenu.addItem(withTitle: "Hide", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
appMenu.addItem(withTitle: "Quit Lethal Company Port", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); appItem.submenu = appMenu
let editItem = NSMenuItem(); menubar.addItem(editItem); let editMenu = NSMenu(title: "Edit")
editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z"); editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c"); editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a"); editItem.submenu = editMenu
let winItem = NSMenuItem(); menubar.addItem(winItem); let winMenu = NSMenu(title: "Window")
winMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m"); winMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"); winItem.submenu = winMenu
app.mainMenu = menubar
app.run()
