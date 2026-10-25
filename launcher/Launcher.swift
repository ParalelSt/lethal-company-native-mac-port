import AppKit
import Foundation

// Native launcher window styled like a web app: sidebar navigation, banner header, rounded cards, a grid of mod tiles,
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
    var padding: CGFloat = 12
    convenience init(_ title: String, fill: NSColor, text: NSColor, bold: Bool = true, target: AnyObject?, action: Selector) {
        self.init(frame: .zero); self.title = title; self.fill = fill; self.textColor = text; self.target = target; self.action = action
        isBordered = false; wantsLayer = true; layer?.cornerRadius = 7; font = .systemFont(ofSize: 12.5, weight: bold ? .semibold : .regular)
        translatesAutoresizingMaskIntoConstraints = false; heightAnchor.constraint(equalToConstant: 30).isActive = true
        setContentCompressionResistancePriority(.required, for: .horizontal); setContentHuggingPriority(.defaultHigh, for: .horizontal); refresh()
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

// MARK: - mods page pieces
/// Rounded toggle pill used for profile chips, category chips and the side panel's category tags.
final class Pill: NSButton {
    var active = false { didSet { refresh() } }
    var pillHeight: CGFloat = 24
    convenience init(_ title: String, height: CGFloat = 24, target: AnyObject?, action: Selector?) {
        self.init(frame: .zero); self.title = title; pillHeight = height; self.target = target; self.action = action
        isBordered = false; wantsLayer = true; layer?.cornerRadius = height / 2; layer?.borderWidth = 1
        font = .systemFont(ofSize: 12.5, weight: .semibold); refresh()
    }
    func refresh() {
        layer?.backgroundColor = (active ? T.card2 : NSColor.clear).cgColor; layer?.borderColor = T.card2.cgColor
        let p = NSMutableParagraphStyle(); p.alignment = .center
        attributedTitle = NSAttributedString(string: title, attributes: [.foregroundColor: active ? NSColor.white : T.muted, .font: font!, .paragraphStyle: p])
    }
    override var intrinsicContentSize: NSSize { NSSize(width: ceil(attributedTitle.size().width) + 24, height: pillHeight) }
}

/// One-line row laid out left to right by hand; views that do not fit are hidden instead of being clipped. An optional
/// trailing view (e.g. the mod count) is pinned to the right end.
final class ChipRow: NSView {
    var views: [NSView] = [] { didSet { oldValue.forEach { $0.removeFromSuperview() }; views.forEach { $0.translatesAutoresizingMaskIntoConstraints = true; addSubview($0) }; needsLayout = true } }
    var trailing: NSView? { didSet { oldValue?.removeFromSuperview(); if let t = trailing { t.translatesAutoresizingMaskIntoConstraints = true; addSubview(t) }; needsLayout = true } }
    var spacing: CGFloat = 6, height: CGFloat = 24
    convenience init(height: CGFloat, spacing: CGFloat = 6) { self.init(frame: .zero); self.height = height; self.spacing = spacing; translatesAutoresizingMaskIntoConstraints = false }
    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize { NSSize(width: NSView.noIntrinsicMetric, height: height) }
    /// Text fields measure their full text (a truncating label's intrinsic width can be squeezed); everything else its intrinsic size.
    static func size(of v: NSView) -> NSSize { if let t = v as? NSTextField, let c = t.cell { let s = c.cellSize; return NSSize(width: ceil(s.width), height: ceil(s.height)) }; return v.intrinsicContentSize }
    override func layout() {
        super.layout()
        var limit = bounds.width
        if let t = trailing { let s = ChipRow.size(of: t); t.frame = NSRect(x: bounds.width - s.width, y: floor((height - s.height) / 2), width: s.width, height: s.height); limit -= s.width + 12 }
        var x: CGFloat = 0, full = false
        for v in views {
            let s = ChipRow.size(of: v)
            if full || x + s.width > limit { full = true; v.isHidden = true; continue }
            v.isHidden = false; v.frame = NSRect(x: x, y: floor((height - s.height) / 2), width: s.width, height: s.height); x += s.width + spacing
        }
    }
}

/// Thunderstore icons: memory cache, then ~/Library/Application Support/LethalCompanyMac/cache/icons/<full_name>.png, then the
/// network. Decoding and downloads run off the main thread; callbacks arrive on the main thread.
final class IconCache {
    static let shared = IconCache()
    let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LethalCompanyMac/cache/icons")
    private let mem = NSCache<NSString, NSImage>()
    private var waiting: [String: [(NSImage?) -> Void]] = [:], failed = Set<String>()
    func cached(_ key: String) -> NSImage? { mem.object(forKey: key as NSString) }
    func image(_ key: String, url: String, _ done: @escaping (NSImage?) -> Void) {
        if let i = cached(key) { done(i); return }
        if failed.contains(key) || key.isEmpty { done(nil); return }
        if waiting[key] != nil { waiting[key]!.append(done); return }
        waiting[key] = [done]
        let file = dir.appendingPathComponent(key.replacingOccurrences(of: "/", with: "_") + ".png")
        DispatchQueue.global(qos: .userInitiated).async {
            if let d = try? Data(contentsOf: file), let img = IconCache.decode(d) { self.finish(key, img); return }
            guard !url.isEmpty, let u = URL(string: url) else { self.finish(key, nil); return }
            URLSession.shared.dataTask(with: u) { data, resp, _ in
                guard let data = data, (resp as? HTTPURLResponse)?.statusCode == 200, let img = IconCache.decode(data) else { self.finish(key, nil); return }
                try? FileManager.default.createDirectory(at: self.dir, withIntermediateDirectories: true); try? data.write(to: file, options: .atomic)
                self.finish(key, img)
            }.resume()
        }
    }
    private func finish(_ key: String, _ img: NSImage?) {
        DispatchQueue.main.async {
            if let i = img { self.mem.setObject(i, forKey: key as NSString) } else { self.failed.insert(key) }
            for cb in self.waiting.removeValue(forKey: key) ?? [] { cb(img) }
        }
    }
    /// Thumbnail at 2x the largest size shown (56pt in the side panel), so 300 tiles stay light in memory.
    static func decode(_ data: Data) -> NSImage? {
        guard let src = CGImageSourceCreateWithData(data as CFData, nil),
              let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 112, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: 56, height: 56))
    }
}

func roundedIcon(_ size: CGFloat) -> NSImageView {
    let v = NSImageView(); v.wantsLayer = true; v.layer?.cornerRadius = size >= 50 ? 12 : 8; v.layer?.masksToBounds = true; v.layer?.backgroundColor = T.card2.cgColor
    v.imageScaling = .scaleProportionallyUpOrDown; v.translatesAutoresizingMaskIntoConstraints = false
    v.widthAnchor.constraint(equalToConstant: size).isActive = true; v.heightAnchor.constraint(equalToConstant: size).isActive = true; return v
}

final class ModTileView: NSView {
    let card = Card(fill: T.card, radius: 10), stripe = NSView(), icon = roundedIcon(36)
    let name = NSTextField(labelWithString: ""), meta = NSTextField(wrappingLabelWithString: ""), desc = NSTextField(wrappingLabelWithString: ""), state = NSTextField(labelWithString: "")
    let check = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    var iconKey = "", onClick: (() -> Void)?
    var selected = false { didSet { card.layer?.borderColor = (selected ? T.accent : T.line).cgColor; card.layer?.borderWidth = selected ? 2 : 1 } }
    override init(frame: NSRect) {
        super.init(frame: frame)
        card.layer?.masksToBounds = true; addSubview(card)
        stripe.wantsLayer = true; stripe.translatesAutoresizingMaskIntoConstraints = false
        name.font = .systemFont(ofSize: 13, weight: .bold); name.textColor = T.text; name.lineBreakMode = .byTruncatingTail
        meta.font = .systemFont(ofSize: 11); meta.textColor = T.muted; meta.maximumNumberOfLines = 2; meta.cell?.truncatesLastVisibleLine = true
        desc.font = .systemFont(ofSize: 11.5); desc.textColor = T.muted; desc.maximumNumberOfLines = 2; desc.cell?.truncatesLastVisibleLine = true
        state.font = .systemFont(ofSize: 11.5, weight: .medium); state.lineBreakMode = .byTruncatingTail
        for v in [name, meta, desc, state] { v.isSelectable = false; v.setContentCompressionResistancePriority(.defaultLow, for: .horizontal) }
        check.translatesAutoresizingMaskIntoConstraints = false
        for v in [stripe, icon, name, meta, desc, state, check] as [NSView] { v.translatesAutoresizingMaskIntoConstraints = false; card.addSubview(v) }
        NSLayoutConstraint.activate([
            card.leadingAnchor.constraint(equalTo: leadingAnchor), card.trailingAnchor.constraint(equalTo: trailingAnchor), card.topAnchor.constraint(equalTo: topAnchor), card.bottomAnchor.constraint(equalTo: bottomAnchor),
            stripe.leadingAnchor.constraint(equalTo: card.leadingAnchor), stripe.topAnchor.constraint(equalTo: card.topAnchor), stripe.bottomAnchor.constraint(equalTo: card.bottomAnchor), stripe.widthAnchor.constraint(equalToConstant: 3),
            icon.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 14), icon.topAnchor.constraint(equalTo: card.topAnchor, constant: 12),
            name.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 10), name.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -12), name.topAnchor.constraint(equalTo: card.topAnchor, constant: 11),
            meta.leadingAnchor.constraint(equalTo: name.leadingAnchor), meta.trailingAnchor.constraint(equalTo: name.trailingAnchor), meta.topAnchor.constraint(equalTo: name.bottomAnchor, constant: 1), meta.heightAnchor.constraint(equalToConstant: 28),
            desc.leadingAnchor.constraint(equalTo: icon.leadingAnchor), desc.trailingAnchor.constraint(equalTo: name.trailingAnchor), desc.topAnchor.constraint(equalTo: card.topAnchor, constant: 60), desc.heightAnchor.constraint(equalToConstant: 30),
            check.leadingAnchor.constraint(equalTo: icon.leadingAnchor), check.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -11),
            state.leadingAnchor.constraint(equalTo: check.trailingAnchor, constant: 2), state.centerYAnchor.constraint(equalTo: check.centerYAnchor), state.trailingAnchor.constraint(lessThanOrEqualTo: card.trailingAnchor, constant: -12),
        ])
        selected = false
    }
    required init?(coder: NSCoder) { fatalError() }
    /// Everything but the checkbox counts as the tile body, so a click anywhere else selects the tile.
    override func hitTest(_ p: NSPoint) -> NSView? {
        guard let v = super.hitTest(p) else { return nil }
        return v === check || v.isDescendant(of: check) ? v : self
    }
    override func mouseDown(with e: NSEvent) { onClick?() }
}

final class ModTileItem: NSCollectionViewItem {
    static let id = NSUserInterfaceItemIdentifier("ModTile")
    override func loadView() { view = ModTileView(frame: NSRect(x: 0, y: 0, width: 210, height: 150)) }
    var tile: ModTileView { view as! ModTileView }
}

/// Flow layout that recomputes tile widths whenever the grid width changes (the side panel opening, window resizes).
final class TileLayout: NSCollectionViewFlowLayout {
    private var lastWidth: CGFloat = 0
    override func shouldInvalidateLayout(forBoundsChange b: NSRect) -> Bool { if b.width != lastWidth { lastWidth = b.width; return true }; return false }
}

// MARK: - launcher
final class Launcher: NSObject, NSApplicationDelegate, NSCollectionViewDataSource, NSCollectionViewDelegateFlowLayout, NSSearchFieldDelegate {
    let kit: URL
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LethalCompanyMac")
    var window: NSWindow!
    var pages: [String: NSView] = [:], navRows: [String: NavRow] = [:], current = "home"
    var heroSub = NSTextField(labelWithString: ""), statusRows: [String: (NSTextField, NSTextField)] = [:]
    var profilesHome = NSPopUpButton(), profiles = NSPopUpButton(), search = NSSearchField()  // `profiles` is hidden: the Mods page's chips select into it
    var profileRow = ChipRow(height: 26, spacing: 8), chipRow = ChipRow(height: 24), modCount = NSTextField(labelWithString: ""), profileSig = ""
    var grid: NSCollectionView!, gridScroll: NSScrollView!, gridToEdge: NSLayoutConstraint!, gridToPanel: NSLayoutConstraint!, bodyToPage: NSLayoutConstraint!, bodyToBar: NSLayoutConstraint!
    var applyBar: NSView!, applyLabel = NSTextField(labelWithString: ""), pendingInstall = Set<String>(), pendingRemove = Set<String>()
    var panel: NSView!, pAction: FlatButton!, pIcon = roundedIcon(56), pIconKey = "", selectedMod: String?, selectedRecord: [String: Any]?, infos: [String: [String: Any]] = [:]
    var pCats = ChipRow(height: 22)
    lazy var pName = label("", size: 16, color: T.text, weight: .bold); lazy var pOwner = label("", size: 12, color: T.muted, wrap: false); lazy var pStats = label("", size: 12, color: T.muted)
    lazy var pDesc = label("", size: 12.5); lazy var pVerdict = label("", size: 12.5, weight: .semibold); lazy var pNotes = label("", size: 11.5); lazy var pDeps = label("", size: 12, color: T.text)
    var log: NSTextView!, logScroll: NSScrollView!, logHeight: NSLayoutConstraint!, drawerLine = NSTextField(labelWithString: "Ready"), drawerArrow = NSTextField(labelWithString: "▸"), spinner: NSProgressIndicator!, drawerOpen = false
    var activityLog: NSTextView!
    var buttons: [NSButton] = []
    var process: Process?
    var allResults: [[String: Any]] = [], results: [[String: Any]] = [], installed: [String: String] = [:], audit: [String: [String: Any]] = [:], category = "All"
    var searchTimer: Timer?, searchSeq = 0, snapshotSelect = false

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
            DispatchQueue.main.asyncAfter(deadline: .now() + 9) { self.snapshot(to: path); NSApp.terminate(nil) }
        }
        if ProcessInfo.processInfo.environment["LC_SNAPSHOT_SELECT"] == "1" {  // open the side panel on the first tile (or as soon as results arrive)
            DispatchQueue.main.asyncAfter(deadline: .now() + 7) { if let f = self.results.first?["full_name"] as? String { self.selectMod(f) } else { self.snapshotSelect = true } }
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
        l.font = .systemFont(ofSize: size, weight: weight); l.textColor = color; l.isSelectable = false; l.translatesAutoresizingMaskIntoConstraints = false
        if !wrap { l.lineBreakMode = .byTruncatingTail; l.setContentCompressionResistancePriority(.defaultLow, for: .horizontal) }
        return l
    }
    func flat(_ title: String, _ sel: Selector, primary: Bool = false) -> FlatButton {
        let b = FlatButton(title, fill: primary ? T.accent : T.card2, text: primary ? NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1) : T.text, target: self, action: sel); buttons.append(b); return b
    }
    func vstack(_ views: [NSView], spacing: CGFloat = 8, insets: NSEdgeInsets = NSEdgeInsets()) -> NSStackView {
        let s = NSStackView(views: views); s.orientation = .vertical; s.alignment = .leading; s.spacing = spacing; s.edgeInsets = insets; s.translatesAutoresizingMaskIntoConstraints = false; return s
    }
    func hstack(_ views: [NSView], spacing: CGFloat = 8) -> NSStackView { let s = NSStackView(views: views); s.spacing = spacing; s.distribution = .fill; s.setClippingResistancePriority(.defaultLow, for: .horizontal); s.translatesAutoresizingMaskIntoConstraints = false; return s }
    func fill(_ child: NSView, in parent: NSView, insets: NSEdgeInsets = NSEdgeInsets()) {
        parent.addSubview(child); child.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([child.leadingAnchor.constraint(equalTo: parent.leadingAnchor, constant: insets.left), child.trailingAnchor.constraint(equalTo: parent.trailingAnchor, constant: -insets.right),
                                     child.topAnchor.constraint(equalTo: parent.topAnchor, constant: insets.top), child.bottomAnchor.constraint(equalTo: parent.bottomAnchor, constant: -insets.bottom)])
    }
    func styledPopup(_ p: NSPopUpButton) { p.translatesAutoresizingMaskIntoConstraints = false; p.font = .systemFont(ofSize: 13) }

    // MARK: window
    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: ProcessInfo.processInfo.environment["LC_SNAPSHOT_SMALL"] == "1" ? 940 : 1040, height: ProcessInfo.processInfo.environment["LC_SNAPSHOT_SMALL"] == "1" ? 640 : 740), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
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
            let v = label("", size: 13, color: T.text, wrap: false); let hint = label("", size: 12, color: T.muted, wrap: false); hint.setContentHuggingPriority(.defaultLow, for: .horizontal)
            statusRows[key] = (v, hint); rows.append(hstack([k, v, hint], spacing: 12))
        }
        let statusStack = vstack(rows, spacing: 9, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)); fill(statusStack, in: status)
        // action cards
        let buildCard = Card(); fill(vstack([label("BUILD / UPDATE GAME", size: 11, color: T.muted, weight: .semibold, wrap: false),
            label("Pick your \"Lethal Company\" folder from a Windows Steam install (Steam › Manage › Browse local files). The launcher checks Steam ownership, extracts the game, swaps the Windows-only parts, compiles the shaders for Metal and installs the app. About an hour the first time, much less afterwards. Run it again when the game updates.", size: 12.5),
            flat("Choose folder and build…", #selector(build), primary: true)], spacing: 10, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)), in: buildCard)
        let updBtns = vstack([flat("Check for game update", #selector(checkGame)), hstack([flat("How it works", #selector(howItWorks)), flat("Quit", #selector(quit))])], spacing: 8)
        let upd = Card(); fill(vstack([label("UPDATES & HELP", size: 11, color: T.muted, weight: .semibold, wrap: false),
            label("The launcher checks for a newer launcher release when it starts. Game updates are detected against Steam's public build; when one ships, copy the new Windows folder over and run Build / Update again.", size: 12.5),
            updBtns], spacing: 10, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)), in: upd)
        let grid = hstack([buildCard, upd], spacing: 14); grid.distribution = .fillEqually; grid.alignment = .top
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
        styledPopup(profiles); profiles.target = self; profiles.action = #selector(profileChanged)  // never shown: the chips below drive it
        // search first, with a pull-down for the profile-wide actions
        search.placeholderString = "Search Thunderstore"; search.delegate = self; search.controlSize = .large; search.font = .systemFont(ofSize: 14); search.translatesAutoresizingMaskIntoConstraints = false
        search.heightAnchor.constraint(equalToConstant: 34).isActive = true; search.setContentHuggingPriority(.defaultLow, for: .horizontal); search.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let more = NSPopUpButton(frame: .zero, pullsDown: true); more.controlSize = .large; more.addItem(withTitle: "⋯"); more.translatesAutoresizingMaskIntoConstraints = false
        for (t, sel) in [("Import profile code…", #selector(importCode)), ("Open profile folder", #selector(openProfile)), ("Update all", #selector(updateMods)), ("Audit profile", #selector(auditProfile)), ("New profile…", #selector(newProfile))] {
            let it = NSMenuItem(title: t, action: sel, keyEquivalent: ""); it.target = self; more.menu?.addItem(it)
        }
        more.widthAnchor.constraint(equalToConstant: 54).isActive = true
        let searchRow = hstack([search, more], spacing: 8)
        modCount = label("", size: 12, color: T.muted, wrap: false); chipRow.trailing = modCount
        let legend = NSTextField(labelWithAttributedString: { () -> NSAttributedString in
            let s = NSMutableAttributedString(); let f = NSFont.systemFont(ofSize: 11)
            for (t, c) in [("stripe: ", T.muted), ("green", T.ok), (" works on Mac · ", T.muted), ("amber", T.warn), (" visuals auto-fixed · ", T.muted), ("red", T.bad), (" needs porting", T.muted)] { s.append(NSAttributedString(string: t, attributes: [.font: f, .foregroundColor: c])) }
            return s }()); legend.translatesAutoresizingMaskIntoConstraints = false; legend.lineBreakMode = .byTruncatingTail; legend.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let header = vstack([title, profileRow, searchRow, chipRow, legend], spacing: 12, insets: NSEdgeInsets(top: 48, left: 28, bottom: 0, right: 28))
        header.setCustomSpacing(14, after: title); header.setCustomSpacing(8, after: chipRow)
        for v in [profileRow, searchRow, chipRow, legend] as [NSView] { v.widthAnchor.constraint(equalTo: header.widthAnchor, constant: -56).isActive = true }
        page.addSubview(header)
        // grid of tiles + side panel
        let layout = TileLayout(); layout.minimumInteritemSpacing = 12; layout.minimumLineSpacing = 12; layout.sectionInset = NSEdgeInsets(top: 4, left: 4, bottom: 4, right: 4); layout.itemSize = NSSize(width: 210, height: 150)
        grid = NSCollectionView(); grid.collectionViewLayout = layout; grid.dataSource = self; grid.delegate = self; grid.backgroundColors = [.clear]; grid.isSelectable = false
        grid.register(ModTileItem.self, forItemWithIdentifier: ModTileItem.id)
        gridScroll = NSScrollView(); gridScroll.documentView = grid; gridScroll.hasVerticalScroller = true; gridScroll.drawsBackground = false; gridScroll.translatesAutoresizingMaskIntoConstraints = false
        panel = buildPanel(); panel.isHidden = true
        applyBar = buildApplyBar(); applyBar.isHidden = true
        for v in [gridScroll, panel, applyBar] as [NSView] { page.addSubview(v) }
        gridToEdge = gridScroll.trailingAnchor.constraint(equalTo: page.trailingAnchor, constant: -24)
        gridToPanel = gridScroll.trailingAnchor.constraint(equalTo: panel.leadingAnchor, constant: -14)
        bodyToPage = gridScroll.bottomAnchor.constraint(equalTo: page.bottomAnchor, constant: -14)
        bodyToBar = gridScroll.bottomAnchor.constraint(equalTo: applyBar.topAnchor, constant: -10)
        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: page.leadingAnchor), header.trailingAnchor.constraint(equalTo: page.trailingAnchor), header.topAnchor.constraint(equalTo: page.topAnchor),
            gridScroll.leadingAnchor.constraint(equalTo: page.leadingAnchor, constant: 24), gridScroll.topAnchor.constraint(equalTo: header.bottomAnchor, constant: 10), gridToEdge, bodyToPage,
            panel.trailingAnchor.constraint(equalTo: page.trailingAnchor, constant: -28), panel.topAnchor.constraint(equalTo: gridScroll.topAnchor, constant: 4), panel.bottomAnchor.constraint(equalTo: gridScroll.bottomAnchor, constant: -4), panel.widthAnchor.constraint(equalToConstant: 300),
            applyBar.leadingAnchor.constraint(equalTo: page.leadingAnchor, constant: 28), applyBar.trailingAnchor.constraint(equalTo: page.trailingAnchor, constant: -28), applyBar.bottomAnchor.constraint(equalTo: page.bottomAnchor, constant: -12),
        ])
        return page
    }

    func buildPanel() -> NSView {
        let card = Card()
        let close = flat("✕", #selector(closePanel)); close.padding = 9
        pName.preferredMaxLayoutWidth = 160; pName.maximumNumberOfLines = 3
        let head = hstack([pIcon, vstack([pName, pOwner], spacing: 2)], spacing: 12); head.alignment = .top
        for l in [pStats, pDesc, pVerdict, pNotes, pDeps] { l.preferredMaxLayoutWidth = 268 }
        pDesc.textColor = T.text
        let depsTitle = label("DEPENDENCIES", size: 11, color: T.muted, weight: .semibold, wrap: false)
        let content = vstack([head, pStats, pCats, pDesc, pVerdict, pNotes, depsTitle, pDeps], spacing: 10, insets: NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16))
        content.setCustomSpacing(14, after: head); content.setCustomSpacing(4, after: pVerdict); content.setCustomSpacing(16, after: pNotes); content.setCustomSpacing(4, after: depsTitle)
        for v in [pStats, pCats, pDesc, pVerdict, pNotes, pDeps] as [NSView] { v.widthAnchor.constraint(equalToConstant: 268).isActive = true }
        let doc = FlippedView(); doc.translatesAutoresizingMaskIntoConstraints = false; doc.addSubview(content)
        NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo: doc.leadingAnchor), content.trailingAnchor.constraint(equalTo: doc.trailingAnchor), content.topAnchor.constraint(equalTo: doc.topAnchor), content.bottomAnchor.constraint(equalTo: doc.bottomAnchor)])
        let scroll = NSScrollView(); scroll.documentView = doc; scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true; scroll.drawsBackground = false; scroll.translatesAutoresizingMaskIntoConstraints = false
        pAction = flat("Install", #selector(panelAction), primary: true)
        let buttons = hstack([pAction, flat("Open on Thunderstore", #selector(openThunderstore))], spacing: 8)
        for v in [scroll, buttons, close] as [NSView] { card.addSubview(v) }
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: card.leadingAnchor), scroll.trailingAnchor.constraint(equalTo: card.trailingAnchor), scroll.topAnchor.constraint(equalTo: card.topAnchor, constant: 1), scroll.bottomAnchor.constraint(equalTo: buttons.topAnchor, constant: -10),
            doc.widthAnchor.constraint(equalTo: scroll.widthAnchor),
            buttons.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 16), buttons.trailingAnchor.constraint(lessThanOrEqualTo: card.trailingAnchor, constant: -16), buttons.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -14),
            close.topAnchor.constraint(equalTo: card.topAnchor, constant: 12), close.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -12),
        ])
        return card
    }

    func buildApplyBar() -> NSView {
        let bar = Card(fill: T.card2, radius: 10)
        applyLabel = label("", size: 13, color: T.text, weight: .semibold, wrap: false)
        let row = hstack([applyLabel, NSView(), flat("Discard", #selector(discardPending)), flat("Apply changes", #selector(applyPending), primary: true)], spacing: 8)
        row.edgeInsets = NSEdgeInsets(top: 9, left: 16, bottom: 9, right: 10); fill(row, in: bar)
        (row.arrangedSubviews[2] as? FlatButton)?.fill = T.card
        return bar
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
        syncProfileChips()
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
    func setBusy(_ b: Bool) { b ? spinner.startAnimation(nil) : spinner.stopAnimation(nil); for x in buttons where x.title != "Clear" && x.title != "Quit" { x.isEnabled = !b }; if !b { drawerLine.stringValue = "Done" }; refreshTiles() }
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
    @objc func profileChanged() {
        UserDefaults.standard.set(profile, forKey: "lc.profile"); profilesHome.selectItem(withTitle: profile)
        pendingInstall.removeAll(); pendingRemove.removeAll(); syncProfileChips()
        reloadInstalled { self.afterInstalledChange() }
    }
    @objc func profileChangedHome() { if let t = profilesHome.titleOfSelectedItem { profiles.selectItem(withTitle: t) }; profileChanged() }
    @objc func profileChipClicked(_ sender: Pill) { guard sender.title != profile else { return }; profiles.selectItem(withTitle: sender.title); profileChanged() }
    /// Rebuilds the profile chips from the hidden `profiles` popup (the source of truth shared with Home) when its items or selection change.
    func syncProfileChips() {
        let names = profiles.itemTitles, sig = names.joined(separator: "\u{1}") + "|" + profile
        if sig == profileSig { return }; profileSig = sig
        var v: [NSView] = [label("Profile", size: 13, color: T.text, weight: .medium, wrap: false)]
        for n in names { let p = Pill(n, height: 26, target: self, action: #selector(profileChipClicked(_:))); p.active = n == profile; v.append(p) }
        v.append(Pill("+ New", height: 26, target: self, action: #selector(newProfile)))
        profileRow.views = v
    }
    func reloadInstalled(_ done: (() -> Void)? = nil) {
        kitJSON(["mods", "json-installed", profile]) { obj in
            if let d = obj as? [String: Any] { self.installed = d["installed"] as? [String: String] ?? [:]; self.audit = d["audit"] as? [String: [String: Any]] ?? [:] }
            done?()
        }
    }
    /// After installs/removes: the "Installed" view needs a new search, everything else just re-renders.
    func afterInstalledChange() { if category == "Installed" { doSearch() } else { refreshTiles() } }
    func controlTextDidChange(_ n: Notification) { searchTimer?.invalidate(); searchTimer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: false) { _ in self.doSearch() } }
    @objc func doSearch() {
        searchSeq += 1; let seq = searchSeq
        kitJSON(["mods", "json-search"] + (category == "Installed" ? ["--installed", profile] : []) + [search.stringValue]) { obj in
            guard seq == self.searchSeq else { return }  // a newer search is in flight
            self.allResults = (obj as? [[String: Any]]) ?? []; self.rebuildCategoryChips(); self.applyFilter()
        }
    }
    func rebuildCategoryChips() {
        var freq: [String: Int] = [:]
        for r in allResults { for c in r["categories"] as? [String] ?? [] { freq[c, default: 0] += 1 } }
        let cats = freq.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }.prefix(10).map { $0.key }
        let titles = ["All", "Installed"] + cats.filter { $0 != "All" && $0 != "Installed" }
        if !titles.contains(category) { category = "All" }
        chipRow.views = titles.map { t in let p = Pill(t, target: self, action: #selector(categoryClicked(_:))); p.active = t == category; return p }
    }
    @objc func categoryClicked(_ sender: Pill) {
        let wasInstalled = category == "Installed"; category = sender.title
        for case let p as Pill in chipRow.views { p.active = p.title == category }
        if wasInstalled != (category == "Installed") { doSearch() } else { applyFilter() }
    }
    func applyFilter() {
        results = category == "All" || category == "Installed" ? allResults : allResults.filter { ($0["categories"] as? [String] ?? []).contains(category) }
        modCount.stringValue = results.count == 1 ? "1 mod" : "\(results.count) mods"; chipRow.needsLayout = true
        grid.reloadData(); gridScroll.contentView.scroll(to: .zero); gridScroll.reflectScrolledClipView(gridScroll.contentView)
        updateApplyBar()
        if snapshotSelect, let f = results.first?["full_name"] as? String { snapshotSelect = false; selectMod(f) }
    }

    // tiles
    func numberOfSections(in cv: NSCollectionView) -> Int { 1 }
    func collectionView(_ cv: NSCollectionView, numberOfItemsInSection s: Int) -> Int { results.count }
    func collectionView(_ cv: NSCollectionView, itemForRepresentedObjectAt ip: IndexPath) -> NSCollectionViewItem {
        let item = cv.makeItem(withIdentifier: ModTileItem.id, for: ip) as! ModTileItem
        if ip.item < results.count { configure(item.tile, results[ip.item]) }
        return item
    }
    /// About 210 wide: as many columns as fit, stretched to fill the row so there is no ragged gap on the right.
    func collectionView(_ cv: NSCollectionView, layout: NSCollectionViewLayout, sizeForItemAt ip: IndexPath) -> NSSize {
        let avail = max(cv.bounds.width, gridScroll.contentView.bounds.width) - 8
        let cols = max(1, floor((avail + 12) / 222)); return NSSize(width: floor((avail - 12 * (cols - 1)) / cols), height: 150)
    }
    func fmtDownloads(_ n: Int) -> String { n >= 1_000_000 ? String(format: "%.1fM", Double(n) / 1e6) : n >= 1000 ? String(format: "%.0fk", Double(n) / 1e3) : "\(n)" }
    /// Mac verdict for a mod: stripe colour, headline and audit notes.
    func verdict(_ full: String) -> (NSColor, String, [String]) {
        guard installed[full] != nil else { return (T.line, "Not installed: the Mac audit runs after install", []) }
        let a = audit[full], notes = a?["notes"] as? [String] ?? []
        switch a?["group"] as? String {
        case "auto": return (T.warn, "Visuals auto-fixed on Mac", notes)
        case "fix": return (T.bad, "Needs porting work on Mac", notes)
        case "ok": return (T.ok, "Works on Mac", notes)
        default: return (T.ok, "Installed, no audit issues recorded", notes)
        }
    }
    func configure(_ tile: ModTileView, _ r: [String: Any]) {
        let full = r["full_name"] as? String ?? ""
        tile.name.stringValue = r["name"] as? String ?? ""
        tile.meta.stringValue = "by \(r["owner"] as? String ?? "") · \(r["version"] as? String ?? "") · \(fmtDownloads(r["downloads"] as? Int ?? 0)) downloads"
        tile.desc.stringValue = r["description"] as? String ?? ""
        let inst = installed[full], pi = pendingInstall.contains(full), pr = pendingRemove.contains(full)
        tile.check.state = (inst != nil && !pr) || pi ? .on : .off
        tile.check.identifier = NSUserInterfaceItemIdentifier(full); tile.check.target = self; tile.check.action = #selector(tileChecked(_:))
        if pi { tile.state.stringValue = "will install"; tile.state.textColor = T.accent }
        else if pr { tile.state.stringValue = "will remove"; tile.state.textColor = T.bad }
        else if let v = inst { tile.state.stringValue = "installed \(v)"; tile.state.textColor = T.ok }
        else { tile.state.stringValue = "not installed"; tile.state.textColor = T.muted }
        tile.stripe.layer?.backgroundColor = verdict(full).0.cgColor
        tile.selected = selectedMod == full
        tile.onClick = { [weak self] in self?.selectMod(full) }
        if tile.iconKey != full { tile.iconKey = full; tile.icon.image = IconCache.shared.cached(full) }
        if tile.icon.image == nil {
            IconCache.shared.image(full, url: r["icon"] as? String ?? "") { [weak tile] img in if let t = tile, t.iconKey == full { t.icon.image = img } }
        }
    }
    @objc func tileChecked(_ b: NSButton) {
        guard let full = b.identifier?.rawValue else { return }
        if installed[full] != nil { if b.state == .on { pendingRemove.remove(full) } else { pendingRemove.insert(full) } }
        else { if b.state == .on { pendingInstall.insert(full) } else { pendingInstall.remove(full) } }
        refreshTiles()
    }
    /// Re-render visible tiles, the side panel and the apply bar in place (no reload, so scrolling and icons stay put).
    func refreshTiles() {
        guard grid != nil else { return }
        for ip in grid.indexPathsForVisibleItems() where ip.item < results.count { if let it = grid.item(at: ip) as? ModTileItem { configure(it.tile, results[ip.item]) } }
        updateApplyBar(); fillPanel()
    }
    func updateApplyBar() {
        var parts: [String] = []
        if !pendingInstall.isEmpty { parts.append("\(pendingInstall.count) to install") }
        if !pendingRemove.isEmpty { parts.append("\(pendingRemove.count) to remove") }
        applyLabel.stringValue = parts.joined(separator: " · ")
        let show = !parts.isEmpty
        if applyBar.isHidden == show { applyBar.isHidden = !show; bodyToPage.isActive = !show; bodyToBar.isActive = show }
    }
    @objc func discardPending() { pendingInstall.removeAll(); pendingRemove.removeAll(); refreshTiles() }
    @objc func applyPending() {
        if pendingInstall.isEmpty && pendingRemove.isEmpty { return }
        var args = ["mods", "apply", profile]
        if !pendingInstall.isEmpty { args += ["--install"] + pendingInstall.sorted() }
        if !pendingRemove.isEmpty { args += ["--remove"] + pendingRemove.sorted() }
        run(args) { self.pendingInstall.removeAll(); self.pendingRemove.removeAll(); self.reloadInstalled { self.afterInstalledChange() } }
    }

    // side panel
    func selectMod(_ full: String?) {
        selectedMod = full; selectedRecord = full.flatMap { f in results.first { $0["full_name"] as? String == f } ?? allResults.first { $0["full_name"] as? String == f } }
        let open = full != nil
        if panel.isHidden == open { panel.isHidden = !open; gridToEdge.isActive = !open; gridToPanel.isActive = open; grid.collectionViewLayout?.invalidateLayout() }
        refreshTiles()
        // the column count just changed: once laid out again, bring the selected tile into view
        if let f = full, let i = results.firstIndex(where: { $0["full_name"] as? String == f }) {
            DispatchQueue.main.async { self.grid.superview?.superview?.layoutSubtreeIfNeeded(); self.grid.scrollToItems(at: [IndexPath(item: i, section: 0)], scrollPosition: .nearestHorizontalEdge) }
        }
        guard let f = full else { return }
        if infos[f] == nil {
            kitJSON(["mods", "json-info", f]) { obj in
                self.infos[f] = obj as? [String: Any] ?? ["error": "failed"]
                if self.selectedMod == f { self.fillPanel() }  // ignore results for a tile that is no longer selected
            }
        }
    }
    @objc func closePanel() { selectMod(nil) }
    func fillPanel() {
        guard let r = selectedRecord, let full = selectedMod, !panel.isHidden else { return }
        if pIconKey != full {
            pIconKey = full; pIcon.image = IconCache.shared.cached(full)
            if pIcon.image == nil { IconCache.shared.image(full, url: r["icon"] as? String ?? "") { img in if self.pIconKey == full { self.pIcon.image = img } } }
        }
        pName.stringValue = r["name"] as? String ?? ""; pOwner.stringValue = "by \(r["owner"] as? String ?? "")"
        var stats = "Version \(r["version"] as? String ?? "?")  ·  \(fmtDownloads(r["downloads"] as? Int ?? 0)) downloads  ·  rating \(r["rating"] as? Int ?? 0)"
        let info = infos[full]
        if let d = info?["date_updated"] as? String, d.count >= 10 { stats += "  ·  updated \(d.prefix(10))" }
        pStats.stringValue = stats
        pCats.views = (r["categories"] as? [String] ?? []).map { Pill($0, height: 22, target: nil, action: nil) }
        pCats.isHidden = pCats.views.isEmpty
        pDesc.stringValue = r["description"] as? String ?? ""
        let (color, headline, notes) = verdict(full)
        pVerdict.stringValue = "● " + headline; pVerdict.textColor = color == T.line ? T.muted : color
        pNotes.stringValue = notes.map { "• " + $0 }.joined(separator: "\n"); pNotes.isHidden = notes.isEmpty
        if let deps = info?["dependencies"] as? [String] {
            pDeps.stringValue = deps.isEmpty ? "None" : deps.map { d -> String in
                let (n, v) = splitRef(d); return v.isEmpty ? n : "\(n)  \(v)" }.joined(separator: "\n")
        } else { pDeps.stringValue = info == nil ? "Loading…" : "Unknown package" }
        let inst = installed[full] != nil
        pAction.title = inst ? "Remove" : "Install"; pAction.fill = inst ? T.card2 : T.accent; pAction.textColor = inst ? T.text : NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1)
    }
    /// "Author-Name-1.2.3" -> ("Author-Name", "1.2.3")
    func splitRef(_ ref: String) -> (String, String) {
        guard let i = ref.lastIndex(of: "-"), ref[ref.index(after: i)...].allSatisfy({ $0.isNumber || $0 == "." }) else { return (ref, "") }
        return (String(ref[..<i]), String(ref[ref.index(after: i)...]))
    }
    @objc func panelAction() {
        guard let f = selectedMod else { return }
        run(["mods", installed[f] != nil ? "remove" : "install", profile, f]) { self.pendingInstall.remove(f); self.pendingRemove.remove(f); self.reloadInstalled { self.afterInstalledChange() } }
    }
    @objc func openThunderstore() {
        guard let r = selectedRecord, let o = r["owner"] as? String, let n = r["name"] as? String, let u = URL(string: "https://thunderstore.io/c/lethal-company/p/\(o)/\(n)/") else { return }
        NSWorkspace.shared.open(u)
    }

    // profile-wide actions (the "⋯" menu)
    @objc func importCode() {
        let a = NSAlert(); a.messageText = "Import profile code"; a.informativeText = "Paste a Thunderstore / r2modman profile code. Its mods go into the \"\(profile)\" profile."
        a.addButton(withTitle: "Import"); a.addButton(withTitle: "Cancel")
        let f = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24)); f.placeholderString = "Profile code"; a.accessoryView = f; a.window.initialFirstResponder = f
        guard a.runModal() == .alertFirstButtonReturn else { return }
        let code = f.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if code.isEmpty { appendLog("Paste a profile code first.\n"); setDrawer(true); return }
        run(["mods", "import", profile, code]) { self.reloadInstalled { self.doSearch() } }
    }
    @objc func auditProfile() { run(["mods", "audit", profile]) { self.reloadInstalled { self.refreshTiles() } } }
    @objc func updateMods() { run(["mods", "update", profile]) { self.reloadInstalled { self.afterInstalledChange() } } }
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
