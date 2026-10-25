import AppKit
import Foundation
import WebKit

// Native launcher window styled like a web app: sidebar navigation, banner header, rounded cards, a grid of mod tiles,
// collapsible log drawer. Every action runs the Python kit ("python3 -m lcport ...") in the kit folder next to this
// app bundle; output streams into the drawer.

/// Paragraph style for one-line labels set through attributedStringValue (which otherwise drops the label's truncation).
let oneLine: NSParagraphStyle = { let p = NSMutableParagraphStyle(); p.lineBreakMode = .byTruncatingTail; return p }()

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
    /// Outlined variant: transparent fill, 1pt accent border, accent text (the tiles' "Undo").
    var outline = false { didSet { refresh() } }
    var padding: CGFloat = 10
    var heightConstraint: NSLayoutConstraint!
    enum Style { case primary, secondary, outline }
    /// 26pt pill, 12pt medium; `bold` (primary actions) uses semibold. Callers may raise the height and font (the hero Play does).
    convenience init(_ title: String, fill: NSColor, text: NSColor, bold: Bool = false, target: AnyObject?, action: Selector?) {
        self.init(frame: .zero); self.title = title; self.fill = fill; self.textColor = text; self.target = target; self.action = action
        isBordered = false; wantsLayer = true; layer?.cornerRadius = 7; font = .systemFont(ofSize: 12, weight: bold ? .semibold : .medium)
        translatesAutoresizingMaskIntoConstraints = false; heightConstraint = heightAnchor.constraint(equalToConstant: 26); heightConstraint.isActive = true
        setContentCompressionResistancePriority(.required, for: .horizontal); setContentHuggingPriority(.defaultHigh, for: .horizontal); refresh()
    }
    /// Primary: accent fill, dark semibold text. Secondary: T.card2 fill, light text. Outline: see `outline`.
    func setStyle(_ s: Style) {
        let size = font?.pointSize ?? 12
        switch s {
        case .primary: outline = false; fill = T.accent; textColor = NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1); font = .systemFont(ofSize: size, weight: .semibold)
        case .secondary: outline = false; fill = T.card2; textColor = T.text; font = .systemFont(ofSize: size, weight: .medium)
        case .outline: outline = true; textColor = T.accent; font = .systemFont(ofSize: size, weight: .semibold)
        }
        refresh()
    }
    func refresh() {
        layer?.backgroundColor = outline ? NSColor.clear.cgColor : (isEnabled ? fill : fill.withAlphaComponent(0.4)).cgColor
        layer?.borderWidth = outline ? 1 : 0; layer?.borderColor = (isEnabled ? T.accent : T.accent.withAlphaComponent(0.4)).cgColor
        let p = NSMutableParagraphStyle(); p.alignment = .center
        let t = NSMutableAttributedString(string: title, attributes: [.foregroundColor: isEnabled ? textColor : textColor.withAlphaComponent(0.6), .font: font!, .paragraphStyle: p])
        if title.hasSuffix("▾") { t.addAttribute(.foregroundColor, value: T.muted, range: NSRange(location: (title as NSString).length - 1, length: 1)) }  // dropdown chevron
        attributedTitle = t
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

/// Two-option switch (Vanilla | Mods) in the theme's colours: a bordered capsule whose selected half is filled with T.card2.
final class SegSwitch: NSView {
    private var items: [NSButton] = []
    var selected = 0 { didSet { refresh() } }
    var onChange: ((Int) -> Void)?
    init(_ titles: [String]) {
        super.init(frame: .zero); wantsLayer = true; translatesAutoresizingMaskIntoConstraints = false
        layer?.cornerRadius = 7; layer?.borderWidth = 1; layer?.masksToBounds = true
        layer?.borderColor = NSColor(srgbRed: 0.227, green: 0.255, blue: 0.306, alpha: 1).cgColor; layer?.backgroundColor = NSColor(white: 0, alpha: 0.2).cgColor
        let bold = NSFont.systemFont(ofSize: 12, weight: .semibold)
        let w = ceil(titles.map { ($0 as NSString).size(withAttributes: [.font: bold]).width }.max() ?? 40) + 28  // equal halves
        var x: NSLayoutXAxisAnchor = leadingAnchor
        for (i, t) in titles.enumerated() {
            let b = NSButton(title: t, target: self, action: #selector(click(_:))); b.tag = i; b.isBordered = false; b.wantsLayer = true; b.translatesAutoresizingMaskIntoConstraints = false
            addSubview(b); items.append(b)
            NSLayoutConstraint.activate([b.leadingAnchor.constraint(equalTo: x), b.topAnchor.constraint(equalTo: topAnchor), b.bottomAnchor.constraint(equalTo: bottomAnchor), b.widthAnchor.constraint(equalToConstant: w)])
            x = b.trailingAnchor
        }
        NSLayoutConstraint.activate([x.constraint(equalTo: trailingAnchor), heightAnchor.constraint(equalToConstant: 28)])
        refresh()
    }
    required init?(coder: NSCoder) { fatalError() }
    @objc func click(_ b: NSButton) { if b.tag != selected { selected = b.tag; onChange?(selected) } }
    func refresh() {
        let p = NSMutableParagraphStyle(); p.alignment = .center
        for b in items {
            let on = b.tag == selected
            b.layer?.backgroundColor = (on ? T.card2 : NSColor.clear).cgColor
            b.attributedTitle = NSAttributedString(string: b.title, attributes: [.foregroundColor: on ? T.text : T.muted, .font: NSFont.systemFont(ofSize: 12, weight: on ? .semibold : .medium), .paragraphStyle: p])
        }
    }
}

// MARK: - mods page pieces
/// Rounded toggle pill used for profile chips and category chips.
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
    /// Thumbnail at 2x the largest size shown (48pt in the mod sheet; 56pt leaves headroom), so 300 tiles stay light in memory.
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

/// Small bordered capsule for the mod sheet's chip row: optional coloured dot, then the text.
final class TagChip: NSView {
    let label = NSTextField(labelWithString: "")
    let height: CGFloat
    init(_ text: String, dot: NSColor? = nil, height: CGFloat = 24) {
        self.height = height; super.init(frame: NSRect(x: 0, y: 0, width: 10, height: height)); wantsLayer = true
        layer?.cornerRadius = height / 2; layer?.borderWidth = 1; layer?.borderColor = T.card2.cgColor; layer?.backgroundColor = NSColor(white: 0, alpha: 0.15).cgColor
        let s = NSMutableAttributedString(), f = NSFont.systemFont(ofSize: 12, weight: .medium)
        if let d = dot { s.append(NSAttributedString(string: "●  ", attributes: [.font: NSFont.systemFont(ofSize: 10), .foregroundColor: d])) }
        s.append(NSAttributedString(string: text, attributes: [.font: f, .foregroundColor: T.text])); label.attributedStringValue = s
        label.isSelectable = false; addSubview(label)
    }
    required init?(coder: NSCoder) { fatalError() }
    override var intrinsicContentSize: NSSize { NSSize(width: ceil(label.cell?.cellSize.width ?? 40) + 22, height: height) }
    override func layout() { super.layout(); let s = label.cell?.cellSize ?? .zero; label.frame = NSRect(x: 11, y: floor((bounds.height - s.height) / 2), width: ceil(s.width), height: ceil(s.height)) }
}

final class ModTileView: NSView {
    let card = Card(fill: T.card, radius: 10), stripe = NSView(), icon = roundedIcon(36)
    let name = NSTextField(labelWithString: ""), meta = NSTextField(wrappingLabelWithString: ""), desc = NSTextField(wrappingLabelWithString: ""), state = NSTextField(labelWithString: "")
    /// Install (primary) / Remove (secondary) / Undo (outline): queues or clears a pending change; Apply in the bottom bar runs them.
    let action = FlatButton("Install", fill: T.accent, text: T.text, bold: true, target: nil, action: nil)
    var iconKey = "", onClick: (() -> Void)?
    /// Open in the mod sheet: 2pt accent border. A queued change: 1pt accent border.
    var selected = false { didSet { border() } }
    var pending = false { didSet { border() } }
    func border() { card.layer?.borderColor = (selected || pending ? T.accent : T.line).cgColor; card.layer?.borderWidth = selected ? 2 : 1 }
    override init(frame: NSRect) {
        super.init(frame: frame)
        card.layer?.masksToBounds = true; addSubview(card)
        stripe.wantsLayer = true; stripe.translatesAutoresizingMaskIntoConstraints = false
        name.font = .systemFont(ofSize: 13, weight: .bold); name.textColor = T.text; name.lineBreakMode = .byTruncatingTail
        meta.font = .systemFont(ofSize: 11); meta.textColor = T.muted; meta.maximumNumberOfLines = 2; meta.cell?.truncatesLastVisibleLine = true
        desc.font = .systemFont(ofSize: 11.5); desc.textColor = T.muted; desc.maximumNumberOfLines = 2; desc.cell?.truncatesLastVisibleLine = true
        state.font = .systemFont(ofSize: 11.5, weight: .medium); state.lineBreakMode = .byTruncatingTail
        for v in [name, meta, desc, state] { v.isSelectable = false; v.setContentCompressionResistancePriority(.defaultLow, for: .horizontal) }
        action.font = .systemFont(ofSize: 11.5, weight: .semibold); action.heightConstraint.constant = 24; action.padding = 11
        for v in [stripe, icon, name, meta, desc, state, action] as [NSView] { v.translatesAutoresizingMaskIntoConstraints = false; card.addSubview(v) }
        NSLayoutConstraint.activate([
            card.leadingAnchor.constraint(equalTo: leadingAnchor), card.trailingAnchor.constraint(equalTo: trailingAnchor), card.topAnchor.constraint(equalTo: topAnchor), card.bottomAnchor.constraint(equalTo: bottomAnchor),
            stripe.leadingAnchor.constraint(equalTo: card.leadingAnchor), stripe.topAnchor.constraint(equalTo: card.topAnchor), stripe.bottomAnchor.constraint(equalTo: card.bottomAnchor), stripe.widthAnchor.constraint(equalToConstant: 3),
            icon.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 14), icon.topAnchor.constraint(equalTo: card.topAnchor, constant: 12),
            name.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 10), name.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -12), name.topAnchor.constraint(equalTo: card.topAnchor, constant: 11),
            meta.leadingAnchor.constraint(equalTo: name.leadingAnchor), meta.trailingAnchor.constraint(equalTo: name.trailingAnchor), meta.topAnchor.constraint(equalTo: name.bottomAnchor, constant: 1), meta.heightAnchor.constraint(equalToConstant: 28),
            desc.leadingAnchor.constraint(equalTo: icon.leadingAnchor), desc.trailingAnchor.constraint(equalTo: name.trailingAnchor), desc.topAnchor.constraint(equalTo: card.topAnchor, constant: 60), desc.heightAnchor.constraint(equalToConstant: 30),
            action.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -12), action.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -10),
            state.leadingAnchor.constraint(equalTo: icon.leadingAnchor), state.centerYAnchor.constraint(equalTo: action.centerYAnchor), state.trailingAnchor.constraint(lessThanOrEqualTo: action.leadingAnchor, constant: -8),
        ])
        border()
    }
    required init?(coder: NSCoder) { fatalError() }
    /// Everything but the button counts as the tile body, so a click anywhere else opens the mod sheet.
    override func hitTest(_ p: NSPoint) -> NSView? {
        guard let v = super.hitTest(p) else { return nil }
        return v === action || v.isDescendant(of: action) ? v : self
    }
    override func mouseDown(with e: NSEvent) { onClick?() }
}

/// The mod sheet's backdrop: a 45% black layer over the whole Mods page. A click outside the card closes the sheet;
/// scrolling stays out of the grid underneath.
final class SheetOverlay: NSView {
    var onClose: (() -> Void)?; weak var card: NSView?
    override func mouseDown(with e: NSEvent) { let p = convert(e.locationInWindow, from: nil); if let c = card, c.frame.contains(p) { return }; onClose?() }
    override func scrollWheel(with e: NSEvent) {}
}

final class ModTileItem: NSCollectionViewItem {
    static let id = NSUserInterfaceItemIdentifier("ModTile")
    override func loadView() { view = ModTileView(frame: NSRect(x: 0, y: 0, width: 210, height: 150)) }
    var tile: ModTileView { view as! ModTileView }
}

/// Flow layout that recomputes tile widths whenever the grid width changes (window resizes).
final class TileLayout: NSCollectionViewFlowLayout {
    private var lastWidth: CGFloat = 0
    override func shouldInvalidateLayout(forBoundsChange b: NSRect) -> Bool { if b.width != lastWidth { lastWidth = b.width; return true }; return false }
}

// MARK: - launcher
final class Launcher: NSObject, NSApplicationDelegate, NSCollectionViewDataSource, NSCollectionViewDelegateFlowLayout, NSSearchFieldDelegate, WKNavigationDelegate {
    let kit: URL
    let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LethalCompanyMac")
    var window: NSWindow!
    var pages: [String: NSView] = [:], navRows: [String: NavRow] = [:], current = "home"
    var heroSub = NSTextField(labelWithString: ""), statusRows: [String: (NSTextField, NSTextField)] = [:], statusCells: [String: NSView] = [:]
    var modeSwitch: SegSwitch!, playButton: FlatButton!, launcherUpdate: Bool?, launcherChecked = false, launcherNoRelease = false
    var profilesHome: FlatButton!, profiles = NSPopUpButton(), search = NSSearchField()  // `profiles` is hidden: the Mods page's chips select into it
    var profileRow = ChipRow(height: 26, spacing: 8), chipRow = ChipRow(height: 24), modCount = NSTextField(labelWithString: ""), profileSig = ""
    var grid: NSCollectionView!, gridScroll: NSScrollView!, bodyToPage: NSLayoutConstraint!, bodyToBar: NSLayoutConstraint!
    var applyBar: NSView!, applyProg: NSProgressIndicator!, modsBusy = false, applyLabel = NSTextField(labelWithString: ""), pendingInstall = Set<String>(), pendingRemove = Set<String>()
    // mod sheet (opened by clicking a tile): header, chips, actions, then the README in a web view
    var sheet: SheetOverlay!, sAction: FlatButton!, sIcon = roundedIcon(48), sIconKey = "", selectedMod: String?, selectedRecord: [String: Any]?, infos: [String: [String: Any]] = [:]
    var sChips = ChipRow(height: 24, spacing: 6), sWeb: WKWebView!, sNav: WKNavigation?, readmes: [String: [String: Any]] = [:], readmeShown: String?
    lazy var sName = label("", size: 16, color: T.text, weight: .bold, wrap: false); lazy var sMeta = label("", size: 12, color: T.muted, wrap: false)
    lazy var sNote = label("", size: 12, color: T.muted, weight: .medium, wrap: false); lazy var sLoading = label("Loading README…", size: 13, color: T.muted, wrap: false)
    lazy var sNoReadme = label("No README available.", size: 13, color: T.text, weight: .semibold, wrap: false); lazy var sFallbackDesc = label("", size: 12.5)
    var sFallback: NSStackView!
    var log: NSTextView!, logScroll: NSScrollView!, logHeight: NSLayoutConstraint!, drawerLine = NSTextField(labelWithString: "Ready"), drawerArrow = NSTextField(labelWithString: "▸"), spinner: NSProgressIndicator!, drawerOpen = false
    // human task status (driven by the kit's "##status / ##progress / ##done / ##fail" lines, which stay out of the log)
    enum TaskState { case idle, busy, done, fail }
    var taskLabel = NSTextField(labelWithString: ""), taskBar: NSProgressIndicator!, taskState = TaskState.idle, taskText = "Ready", taskPct: Double?
    var barVisible = false, barGen = 0, rawOut = Data(), outBuf = "", midLine = false
    var activityLog: NSTextView!
    var buttons: [NSButton] = []
    var process: Process?
    var allResults: [[String: Any]] = [], results: [[String: Any]] = [], installed: [String: String] = [:], audit: [String: [String: Any]] = [:], category = "All"
    var searchTimer: Timer?, searchSeq = 0, snapshotSelect = false, snapshotPending = false, snapshotSheetPath: String?
    var unityInfo: [String: Any]?, unityCheckedAt: Date?  // last "check-unity" answer: {"hub", "signed_in", "editor"}; asked at most every 30 s

    override init() { kit = Bundle.main.bundleURL.deletingLastPathComponent(); super.init() }

    func applicationDidFinishLaunching(_ n: Notification) {
        buildWindow(); refreshStatus()
        let icns = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Lethal Company.app/Contents/Resources/PlayerIcon.icns")
        if let img = NSImage(contentsOf: icns) { NSApp.applicationIconImage = img }
        Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refreshStatus() }
        NSApp.activate(ignoringOtherApps: true)
        reloadInstalled { self.doSearch() }
        kitJSON(["self-update", "--json"]) { obj in  // "up to date" / "update available" in the status grid
            self.launcherChecked = true
            if let d = obj as? [String: Any] {
                if d["latest"] as? String != nil { self.launcherUpdate = d["available"] as? Bool ?? false }
                self.launcherNoRelease = d["state"] as? String == "none"
            }
            self.refreshStatus()
        }
        if ProcessInfo.processInfo.environment["LC_SNAPSHOT_BUSY"] == "1" {  // review the progress UI: a fake build at step 4 of 9
            DispatchQueue.main.asyncAfter(deadline: .now() + 6.5) {
                self.beginTask(["build"]); self.setBusy(true)
                self.consume("==> Unity: build the macOS app (compiles every shader for Metal; 30-60 min)\n##status compiling shaders (4/9)\n##progress 44\n")
                self.setDrawer(true)
            }
        }
        if ProcessInfo.processInfo.environment["LC_SNAPSHOT_MODSBUSY"] == "1" {  // review the Mods tab bar while a mods command runs
            DispatchQueue.main.asyncAfter(deadline: .now() + 6.5) {
                self.show("mods"); self.pendingInstall = ["A-One", "B-Two"]; self.pendingRemove = []
                self.beginTask(["mods", "apply"]); self.modsBusy = true; self.setBusy(true)
                self.consume("##status Downloading MoreCompany 1.14.0 (2 of 5)\n##progress 37\n")
            }
        }
        if ProcessInfo.processInfo.environment["LC_SNAPSHOT_MENU"] == "1", let path = ProcessInfo.processInfo.environment["LC_SNAPSHOT"] {
            DispatchQueue.main.asyncAfter(deadline: .now() + 8) {  // the menu tracks modally, so schedule the snapshot first
                self.setMode("mods")
                let t = Timer(timeInterval: 1, repeats: false) { _ in self.snapshot(to: path); exit(0) }  // common modes: a GCD block would not run while the menu tracks
                RunLoop.main.add(t, forMode: .common)
                self.openProfileMenu()
            }
        }
        let env = ProcessInfo.processInfo.environment, sheetShot = env["LC_SNAPSHOT_SELECT"] == "1"
        if let path = env["LC_SNAPSHOT"], env["LC_SNAPSHOT_MENU"] != "1" {
            if let tab = env["LC_SNAPSHOT_TAB"] { show(tab) }
            if sheetShot {  // the sheet's README decides when: 4 s after it finished loading (or at the latest after 60 s)
                snapshotSheetPath = path
                DispatchQueue.main.asyncAfter(deadline: .now() + 60) { self.snapshot(to: path); NSApp.terminate(nil) }
            } else { DispatchQueue.main.asyncAfter(deadline: .now() + 9) { self.snapshot(to: path); NSApp.terminate(nil) } }
        }
        if sheetShot {  // open the mod sheet (MoreCompany, else the first tile) as soon as results are there
            DispatchQueue.main.asyncAfter(deadline: .now() + 7) { self.show("mods"); if let f = self.snapshotSheetMod() { self.openSheet(f) } else { self.snapshotSelect = true } }
        }
        if env["LC_SNAPSHOT_PENDING"] == "1" {  // review the tile states: one queued install and one queued remove, no busy state
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { self.show("mods"); if !self.results.isEmpty { self.injectPending() } else { self.snapshotPending = true } }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func snapshot(to path: String) {
        var shot = CGWindowListCreateImage(.null, .optionIncludingWindow, CGWindowID(window.windowNumber), [.boundsIgnoreFraming, .bestResolution])
        if ProcessInfo.processInfo.environment["LC_SNAPSHOT_MENU"] == "1" {  // screen region of the window, so the open menu is in the picture
            let f = window.frame, h = NSScreen.screens.first?.frame.height ?? 0
            let rect = CGRect(x: f.minX, y: h - f.maxY, width: f.width, height: f.height)
            // only this app's on-screen windows (the window plus its open menu), so system prompts from other processes stay out of the picture
            let mine = ((CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]]) ?? []).filter { ($0[kCGWindowOwnerPID as String] as? Int32) == getpid() }.compactMap { $0[kCGWindowNumber as String] as? UInt32 }
            var raw = mine.map { UnsafeRawPointer(bitPattern: UInt($0)) }  // CGWindowIDs stored as raw pointer values, as the API expects
            if let arr = CFArrayCreate(nil, &raw, raw.count, nil) { shot = CGImage(windowListFromArrayScreenBounds: rect, windowArray: arr, imageOption: [.bestResolution]) }
        }
        guard let cg = shot else { return }
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
        let b = FlatButton(title, fill: primary ? T.accent : T.card2, text: primary ? NSColor(srgbRed: 0.10, green: 0.05, blue: 0.02, alpha: 1) : T.text, bold: primary, target: self, action: sel); buttons.append(b); return b
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
        // Vanilla | Mods switch (+ the profile popup in Mods mode), then one wide Play that follows the switch
        modeSwitch = SegSwitch(["Vanilla", "Mods"]); modeSwitch.onChange = { [weak self] i in self?.setMode(i == 1 ? "mods" : "vanilla") }
        profilesHome = flat("Default  ▾", #selector(openProfileMenu)); profilesHome.fill = T.card2; profilesHome.setAccessibilityLabel("Profile")
        let modeRow = hstack([modeSwitch, profilesHome], spacing: 10)
        playButton = flat("▶  Play", #selector(playSelected), primary: true); playButton.heightConstraint.constant = 38
        playButton.font = .systemFont(ofSize: 14, weight: .bold); playButton.layer?.cornerRadius = 8; playButton.refresh()
        playButton.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let heroStack = vstack([title, heroSub, modeRow, playButton], spacing: 10, insets: NSEdgeInsets(top: 54, left: 32, bottom: 26, right: 32))
        heroStack.setCustomSpacing(6, after: title); heroStack.setCustomSpacing(16, after: heroSub); heroStack.setCustomSpacing(12, after: modeRow); fill(heroStack, in: hero)
        playButton.widthAnchor.constraint(equalTo: heroStack.widthAnchor, constant: -64).isActive = true
        setMode(UserDefaults.standard.string(forKey: "lc.mode") == "mods" ? "mods" : "vanilla")
        // status card
        // status card: 2x2 grid, each cell a caption, a bold value and one short hint (the long hint is the tooltip)
        let status = Card(); var cells: [NSView] = []
        for (key, name) in [("game", "Game"), ("steam", "Steam"), ("unity", "Unity"), ("launcher", "Launcher")] {
            let cap = label(name.uppercased(), size: 10.5, color: T.muted, weight: .semibold, wrap: false)
            let v = label("", size: 13, color: T.text, weight: .bold, wrap: false); v.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
            let hint = label("", size: 12, color: T.muted, wrap: false); hint.setContentHuggingPriority(.defaultLow, for: .horizontal)
            let cell = vstack([cap, hstack([v, hint], spacing: 6)], spacing: 3)
            statusRows[key] = (v, hint); statusCells[key] = cell; cells.append(cell)
        }
        let gridRows = [hstack([cells[0], cells[1]], spacing: 16), hstack([cells[2], cells[3]], spacing: 16)]
        let statusStack = vstack(gridRows, spacing: 12, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)); fill(statusStack, in: status)
        for r in gridRows { r.distribution = .fillEqually; r.alignment = .top; r.widthAnchor.constraint(equalTo: statusStack.widthAnchor, constant: -32).isActive = true }
        // action cards
        let buildCard = Card(); fill(vstack([label("BUILD / UPDATE GAME", size: 11, color: T.muted, weight: .semibold, wrap: false),
            label("Pick your Lethal Company folder from a Windows Steam install. The launcher installs Unity Hub and the exact editor version itself; you sign in to Unity once with a free account. About an hour the first time, much less afterwards. Run it again when the game updates.", size: 12.5),
            flat("Choose folder and build…", #selector(build), primary: true)], spacing: 10, insets: NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)), in: buildCard)
        let updBtns = vstack([hstack([flat("Check for game update", #selector(checkGame)), flat("Add to Steam", #selector(addToSteam))]), hstack([flat("How it works", #selector(howItWorks)), flat("Quit", #selector(quit))])], spacing: 8)
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
        // grid of tiles; the mod sheet lies over the whole page when open
        let layout = TileLayout(); layout.minimumInteritemSpacing = 12; layout.minimumLineSpacing = 12; layout.sectionInset = NSEdgeInsets(top: 4, left: 4, bottom: 4, right: 4); layout.itemSize = NSSize(width: 210, height: 150)
        grid = NSCollectionView(); grid.collectionViewLayout = layout; grid.dataSource = self; grid.delegate = self; grid.backgroundColors = [.clear]; grid.isSelectable = false
        grid.register(ModTileItem.self, forItemWithIdentifier: ModTileItem.id)
        gridScroll = NSScrollView(); gridScroll.documentView = grid; gridScroll.hasVerticalScroller = true; gridScroll.drawsBackground = false; gridScroll.translatesAutoresizingMaskIntoConstraints = false
        applyBar = buildApplyBar(); applyBar.isHidden = true
        for v in [gridScroll, applyBar] as [NSView] { page.addSubview(v) }
        bodyToPage = gridScroll.bottomAnchor.constraint(equalTo: page.bottomAnchor, constant: -14)
        bodyToBar = gridScroll.bottomAnchor.constraint(equalTo: applyBar.topAnchor, constant: -10)
        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: page.leadingAnchor), header.trailingAnchor.constraint(equalTo: page.trailingAnchor), header.topAnchor.constraint(equalTo: page.topAnchor),
            gridScroll.leadingAnchor.constraint(equalTo: page.leadingAnchor, constant: 24), gridScroll.topAnchor.constraint(equalTo: header.bottomAnchor, constant: 10),
            gridScroll.trailingAnchor.constraint(equalTo: page.trailingAnchor, constant: -24), bodyToPage,
            applyBar.leadingAnchor.constraint(equalTo: page.leadingAnchor, constant: 28), applyBar.trailingAnchor.constraint(equalTo: page.trailingAnchor, constant: -28), applyBar.bottomAnchor.constraint(equalTo: page.bottomAnchor, constant: -12),
        ])
        sheet = buildSheet(); sheet.isHidden = true; fill(sheet, in: page)  // added last: above the grid, the header and the bar
        return page
    }

    /// The mod sheet: a dimmed backdrop over the Mods page and a card (inset 24pt, at most 760pt wide) with the mod's header,
    /// chips (Mac verdict, categories, dependencies), Install / Remove and Thunderstore buttons, and the README below a separator.
    func buildSheet() -> SheetOverlay {
        let overlay = SheetOverlay(); overlay.wantsLayer = true; overlay.layer?.backgroundColor = NSColor(white: 0, alpha: 0.45).cgColor
        overlay.onClose = { [weak self] in self?.closeSheet() }
        let card = Card(fill: T.card, radius: 12); overlay.card = card; overlay.addSubview(card)
        card.layer?.shadowColor = NSColor.black.cgColor; card.layer?.shadowOpacity = 0.55; card.layer?.shadowRadius = 24; card.layer?.shadowOffset = CGSize(width: 0, height: -10)
        let clip = NSView(); clip.wantsLayer = true; clip.layer?.cornerRadius = 12; clip.layer?.masksToBounds = true; fill(clip, in: card)  // rounds the web view's corners
        // the "✕", Install / Remove and Thunderstore buttons stay usable while a task runs, so they are not in `buttons`
        let close = FlatButton("✕", fill: T.card2, text: T.text, target: self, action: #selector(closeSheet)); close.padding = 9
        sAction = FlatButton("Install", fill: T.accent, text: T.text, bold: true, target: self, action: #selector(sheetAction))
        let thunder = FlatButton("Open on Thunderstore", fill: T.card2, text: T.text, target: self, action: #selector(openThunderstore))
        sName.font = .systemFont(ofSize: 16, weight: .bold)
        let titles = vstack([sName, sMeta], spacing: 3)
        let head = hstack([sIcon, titles], spacing: 12); head.alignment = .centerY
        let actions = hstack([sAction, thunder, sNote], spacing: 8); actions.setCustomSpacing(14, after: thunder)
        let sep = NSView(); sep.wantsLayer = true; sep.layer?.backgroundColor = T.line.cgColor; sep.translatesAutoresizingMaskIntoConstraints = false
        let cfg = WKWebViewConfiguration(); cfg.defaultWebpagePreferences.allowsContentJavaScript = false  // the page also carries a no-script CSP
        sWeb = WKWebView(frame: .zero, configuration: cfg); sWeb.navigationDelegate = self; sWeb.translatesAutoresizingMaskIntoConstraints = false; sWeb.isHidden = true
        sWeb.underPageBackgroundColor = T.card
        sFallbackDesc.textColor = T.muted; sFallback = vstack([sNoReadme, sFallbackDesc], spacing: 6); sFallback.isHidden = true
        for v in [head, close, sChips, actions, sep, sWeb, sLoading, sFallback] as [NSView] { v.translatesAutoresizingMaskIntoConstraints = false; clip.addSubview(v) }
        let wide = card.widthAnchor.constraint(equalTo: overlay.widthAnchor, constant: -48); wide.priority = .defaultHigh
        NSLayoutConstraint.activate([
            card.topAnchor.constraint(equalTo: overlay.topAnchor, constant: 24), card.bottomAnchor.constraint(equalTo: overlay.bottomAnchor, constant: -24), card.centerXAnchor.constraint(equalTo: overlay.centerXAnchor),
            card.widthAnchor.constraint(lessThanOrEqualToConstant: 760), card.widthAnchor.constraint(lessThanOrEqualTo: overlay.widthAnchor, constant: -48), wide,
            close.topAnchor.constraint(equalTo: clip.topAnchor, constant: 14), close.trailingAnchor.constraint(equalTo: clip.trailingAnchor, constant: -14),
            head.topAnchor.constraint(equalTo: clip.topAnchor, constant: 20), head.leadingAnchor.constraint(equalTo: clip.leadingAnchor, constant: 20), head.trailingAnchor.constraint(lessThanOrEqualTo: close.leadingAnchor, constant: -12),
            sChips.topAnchor.constraint(equalTo: head.bottomAnchor, constant: 14), sChips.leadingAnchor.constraint(equalTo: clip.leadingAnchor, constant: 20), sChips.trailingAnchor.constraint(equalTo: clip.trailingAnchor, constant: -20),
            actions.topAnchor.constraint(equalTo: sChips.bottomAnchor, constant: 14), actions.leadingAnchor.constraint(equalTo: clip.leadingAnchor, constant: 20), actions.trailingAnchor.constraint(lessThanOrEqualTo: clip.trailingAnchor, constant: -20),
            sep.topAnchor.constraint(equalTo: actions.bottomAnchor, constant: 16), sep.leadingAnchor.constraint(equalTo: clip.leadingAnchor), sep.trailingAnchor.constraint(equalTo: clip.trailingAnchor), sep.heightAnchor.constraint(equalToConstant: 1),
            sWeb.topAnchor.constraint(equalTo: sep.bottomAnchor), sWeb.leadingAnchor.constraint(equalTo: clip.leadingAnchor), sWeb.trailingAnchor.constraint(equalTo: clip.trailingAnchor), sWeb.bottomAnchor.constraint(equalTo: clip.bottomAnchor),
            sLoading.topAnchor.constraint(equalTo: sep.bottomAnchor, constant: 18), sLoading.leadingAnchor.constraint(equalTo: clip.leadingAnchor, constant: 20),
            sFallback.topAnchor.constraint(equalTo: sep.bottomAnchor, constant: 18), sFallback.leadingAnchor.constraint(equalTo: clip.leadingAnchor, constant: 20), sFallback.trailingAnchor.constraint(lessThanOrEqualTo: clip.trailingAnchor, constant: -20),
            sFallbackDesc.widthAnchor.constraint(lessThanOrEqualToConstant: 640),
        ])
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in  // Escape closes the sheet
            guard let s = self, e.keyCode == 53, !s.sheet.isHidden, e.window === s.window else { return e }
            s.closeSheet(); return nil
        }
        return overlay
    }

    func buildApplyBar() -> NSView {
        let bar = Card(fill: T.card2, radius: 10)
        applyLabel = label("", size: 13, color: T.text, weight: .semibold, wrap: false)
        applyProg = NSProgressIndicator(); applyProg.style = .bar; applyProg.minValue = 0; applyProg.maxValue = 100; applyProg.isHidden = true
        applyProg.translatesAutoresizingMaskIntoConstraints = false; applyProg.widthAnchor.constraint(equalToConstant: 200).isActive = true
        let row = hstack([applyLabel, applyProg, NSView(), flat("Discard", #selector(discardPending)), flat("Apply changes", #selector(applyPending), primary: true)], spacing: 8)
        row.edgeInsets = NSEdgeInsets(top: 9, left: 16, bottom: 9, right: 10); fill(row, in: bar)
        (row.arrangedSubviews[3] as? FlatButton)?.fill = T.card
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
        drawerArrow.font = .systemFont(ofSize: 12); drawerArrow.textColor = T.muted; drawerLine.font = .systemFont(ofSize: 12, weight: .medium); drawerLine.textColor = T.muted; drawerLine.lineBreakMode = .byTruncatingTail
        drawerLine.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let bar = hstack([drawerArrow, drawerLine, NSView(), spinner], spacing: 8); bar.edgeInsets = NSEdgeInsets(top: 0, left: 16, bottom: 0, right: 16)
        bar.heightAnchor.constraint(equalToConstant: 30).isActive = true; bar.addGestureRecognizer(NSClickGestureRecognizer(target: self, action: #selector(toggleDrawer)))
        // expanded part: the human status line and progress bar, then the raw log
        taskLabel = label("Ready", size: 13, color: T.text, wrap: false)
        taskBar = NSProgressIndicator(); taskBar.style = .bar; taskBar.controlSize = .small; taskBar.minValue = 0; taskBar.maxValue = 100; taskBar.isIndeterminate = true; taskBar.translatesAutoresizingMaskIntoConstraints = false; taskBar.isHidden = true
        let statusBox = vstack([taskLabel, taskBar], spacing: 7, insets: NSEdgeInsets(top: 4, left: 16, bottom: 10, right: 16))
        taskLabel.widthAnchor.constraint(equalTo: statusBox.widthAnchor, constant: -32).isActive = true; taskBar.widthAnchor.constraint(equalTo: statusBox.widthAnchor, constant: -32).isActive = true
        log = NSTextView(); log.isEditable = false; log.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular); log.backgroundColor = T.canvas; log.textColor = T.text
        log.isVerticallyResizable = true; log.isHorizontallyResizable = false; log.autoresizingMask = [.width]; log.textContainer?.widthTracksTextView = true; log.textContainerInset = NSSize(width: 10, height: 6)
        logScroll = NSScrollView(); logScroll.documentView = log; logScroll.hasVerticalScroller = true; logScroll.drawsBackground = false; logScroll.translatesAutoresizingMaskIntoConstraints = false
        let details = NSView(); details.wantsLayer = true; details.layer?.masksToBounds = true; details.translatesAutoresizingMaskIntoConstraints = false
        let inner = vstack([statusBox, logScroll], spacing: 0); details.addSubview(inner)
        statusBox.widthAnchor.constraint(equalTo: inner.widthAnchor).isActive = true; logScroll.widthAnchor.constraint(equalTo: inner.widthAnchor).isActive = true
        let fillBottom = inner.bottomAnchor.constraint(equalTo: details.bottomAnchor); fillBottom.priority = .defaultHigh  // gives way while collapsed
        let logFallback = logScroll.heightAnchor.constraint(equalToConstant: 190); logFallback.priority = .defaultLow
        NSLayoutConstraint.activate([inner.leadingAnchor.constraint(equalTo: details.leadingAnchor), inner.trailingAnchor.constraint(equalTo: details.trailingAnchor), inner.topAnchor.constraint(equalTo: details.topAnchor), fillBottom, logFallback])
        logHeight = details.heightAnchor.constraint(equalToConstant: 0); logHeight.isActive = true
        let stack = vstack([bar, details], spacing: 0); fill(stack, in: d)
        bar.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true; details.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        NSLayoutConstraint.activate([top.leadingAnchor.constraint(equalTo: d.leadingAnchor), top.trailingAnchor.constraint(equalTo: d.trailingAnchor), top.topAnchor.constraint(equalTo: d.topAnchor), top.heightAnchor.constraint(equalToConstant: 1)])
        renderTask()
        return d
    }
    @objc func toggleDrawer() { setDrawer(!drawerOpen) }
    func setDrawer(_ open: Bool) {
        drawerOpen = open; drawerArrow.stringValue = open ? "▾" : "▸"; renderTask()
        NSAnimationContext.runAnimationGroup { ctx in ctx.duration = 0.18; logHeight.animator().constant = open ? 250 : 0 }
    }

    // MARK: task status (kit control lines)
    /// "✓ text" in green for done, the whole text in T.bad for a failure, muted when idle.
    func taskString(_ size: CGFloat) -> NSAttributedString {
        let f = NSFont.systemFont(ofSize: size, weight: .medium), s = NSMutableAttributedString()
        switch taskState {
        case .done: s.append(NSAttributedString(string: "✓  ", attributes: [.font: NSFont.systemFont(ofSize: size, weight: .bold), .foregroundColor: T.ok])); s.append(NSAttributedString(string: taskText, attributes: [.font: f, .foregroundColor: T.text]))
        case .fail: s.append(NSAttributedString(string: taskText, attributes: [.font: f, .foregroundColor: T.bad]))
        case .busy: s.append(NSAttributedString(string: taskText, attributes: [.font: f, .foregroundColor: T.text]))
        case .idle: s.append(NSAttributedString(string: taskText, attributes: [.font: f, .foregroundColor: T.muted]))
        }
        s.addAttribute(.paragraphStyle, value: oneLine, range: NSRange(location: 0, length: s.length)); return s
    }
    func renderTask() {
        let big = taskString(13); taskLabel.attributedStringValue = big
        if drawerOpen { drawerLine.attributedStringValue = NSAttributedString(string: "Hide log", attributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium), .foregroundColor: T.muted, .paragraphStyle: oneLine]) }
        else {  // collapsed: the same human status, plus the percentage while it runs
            let line = NSMutableAttributedString(attributedString: taskString(12))
            if taskState == .busy, let p = taskPct { line.append(NSAttributedString(string: "  ·  \(Int(p))%", attributes: [.font: NSFont.systemFont(ofSize: 12), .foregroundColor: T.muted, .paragraphStyle: oneLine])) }
            drawerLine.attributedStringValue = line
        }
        if modsBusy { updateApplyBar() }
        taskBar.isHidden = !barVisible || taskState == .fail
        if let p = taskPct { taskBar.isIndeterminate = false; taskBar.stopAnimation(nil); taskBar.doubleValue = p }
        else { taskBar.isIndeterminate = true; if barVisible { taskBar.startAnimation(nil) } else { taskBar.stopAnimation(nil) } }
    }
    /// A task starts: a first human line until the kit reports its own, and an indeterminate bar.
    func beginTask(_ args: [String]) {
        let first: [String: String] = ["play": "Launching...", "play-modded": "Launching with mods...", "build": "Starting the build...", "mods": "Working on your mods...",
                                       "check-update": "Checking for a game update...", "self-update": "Checking for a launcher update...", "steam-shortcut": "Adding to Steam..."]
        taskState = .busy; taskText = first[args.first ?? ""] ?? "Working..."; taskPct = nil; barVisible = true; barGen += 1
        rawOut.removeAll(); outBuf = ""; midLine = false; renderTask()
    }
    /// The task ended: fill in a result line if the kit printed none, then hide the bar shortly after.
    func endTask(_ code: Int32) {
        if !outBuf.isEmpty { let rest = outBuf; outBuf = ""; line(rest) }
        if code != 0 && taskState != .fail { _ = control("##fail Something went wrong, see Activity") }
        else if code == 0 && taskState == .busy { _ = control("##done Done") }
        barGen += 1; let gen = barGen
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { if gen == self.barGen { self.barVisible = false; self.renderTask() } }
    }
    /// Raw process output: buffered until it decodes as UTF-8, then split into lines.
    func feed(_ d: Data) {
        rawOut.append(d)
        if let s = String(data: rawOut, encoding: .utf8) { rawOut.removeAll(); consume(s) }
        else if rawOut.count > 8192 { let s = String(decoding: rawOut, as: UTF8.self); rawOut.removeAll(); consume(s) }
    }
    /// Complete lines go through `line`; a trailing partial line is shown at once unless it could be the start of a control line.
    func consume(_ s: String) {
        outBuf += s
        while let r = outBuf.range(of: "\n") { let l = String(outBuf[..<r.lowerBound]); outBuf.removeSubrange(..<r.upperBound); line(l) }
        if !outBuf.isEmpty && (midLine || !(outBuf.hasPrefix("##") || outBuf == "#")) { appendLog(outBuf); outBuf = ""; midLine = true }
    }
    func line(_ l: String) {
        if midLine { midLine = false; appendLog(l + "\n"); return }
        if l.hasPrefix("##") && control(l) { return }
        appendLog(l + "\n")
    }
    /// "##status <text>", "##progress <0-100>", "##done <text>", "##fail <text>". Returns false for anything else (it is logged).
    func control(_ l: String) -> Bool {
        let body = l.dropFirst(2), sp = body.firstIndex(of: " ") ?? body.endIndex
        let kind = String(body[..<sp]), text = String(body[sp...]).trimmingCharacters(in: .whitespaces)
        switch kind {
        case "status": taskState = .busy; taskText = text
        case "progress": guard let v = Double(text) else { return false }; taskPct = min(100, max(0, v))
        case "done": taskState = .done; taskText = text.isEmpty ? "Done" : text; taskPct = 100
        case "fail": taskState = .fail; taskText = text.isEmpty ? "Something went wrong, see Activity" : text
        default: return false
        }
        renderTask(); return true
    }

    func show(_ id: String) {
        current = id
        for (k, p) in pages { p.isHidden = k != id }
        for (k, r) in navRows { r.selected = k == id }
    }

    // MARK: status
    func refreshStatus() {
        let app = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Lethal Company.app")
        var gameV = "not built", gameH = "Use Build / Update game below.", gameS = "use Build / Update", gameC = T.warn
        if let data = try? Data(contentsOf: support.appendingPathComponent("state.json")), let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any], FileManager.default.fileExists(atPath: app.path) {
            let built = j["built"] as? String ?? "?"
            gameV = "ready"; gameH = "built \(built) · Unity \(j["unity"] as? String ?? "?") · in ~/Applications"; gameS = builtAgo(built); gameC = T.ok
        } else if FileManager.default.fileExists(atPath: app.path) { gameV = "installed"; gameH = "~/Applications/Lethal Company.app"; gameS = "in ~/Applications"; gameC = T.ok }
        set("game", gameV, gameH, gameC, short: gameS)
        var shortcut = false
        if let data = try? Data(contentsOf: support.appendingPathComponent("state.json")), let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let sc = j["steam_shortcuts"] as? [String: Any], !sc.isEmpty { shortcut = true }
        let steam = isRunning("steam_osx"); set("steam", steam ? "running" : "not running", (shortcut ? "added as shortcut" : "not added") + " · " + (steam ? "signed-in account must own the game" : "started automatically when you play or build"), steam ? T.ok : T.warn,
                                              short: steam ? (shortcut ? "shortcut added" : "no shortcut yet") : "opens when you play")
        if unityCheckedAt == nil || Date().timeIntervalSince(unityCheckedAt!) >= 30 {
            unityCheckedAt = Date()
            kitJSON(["check-unity"]) { obj in if let d = obj as? [String: Any] { self.unityInfo = d; self.refreshStatus() } }
        }
        if let u = unityInfo {
            let signedIn = u["signed_in"] as? Bool ?? false, signTip = signedIn ? "" : " · not signed in: Build opens Unity Hub so you can sign in once"
            if let editor = u["editor"] as? String {
                let ver = URL(fileURLWithPath: editor).deletingLastPathComponent().lastPathComponent
                set("unity", "ready", "editor \(ver) at \(editor)" + signTip, T.ok, short: ver)
            } else if u["hub"] as? String != nil {
                if signedIn { set("unity", "hub ready", "signed in · Build installs the editor through Unity Hub", T.ok, short: "editor installs with Build") }
                else { set("unity", "hub ready", "Unity Hub is installed but has no licence: Build opens it, you sign in once with a free account", T.warn, short: "sign in needed") }
            } else { set("unity", "installs with Build", "Build installs Unity Hub and the editor; you sign in to Unity once with a free account", T.muted, short: "") }
        } else { set("unity", "checking…", "Checking Unity Hub, the Unity sign-in and the editor", T.muted, short: "") }
        let upd = !launcherChecked ? ("checking…", "Checking GitHub for a newer launcher release")
            : launcherUpdate == nil ? (launcherNoRelease ? ("no release published", "No launcher release is published on GitHub yet") : ("update check failed", "Could not reach GitHub to check for a newer launcher"))
            : launcherUpdate! ? ("update available", "A newer launcher is out: use Check for launcher update") : ("up to date", "This is the newest launcher release")
        set("launcher", version(), upd.1, T.text, short: upd.0)
        (window.contentView?.subviews.first?.subviews.compactMap { $0 as? NSStackView }.last?.arrangedSubviews.first as? NSTextField)?.stringValue = "Launcher \(version())"
        let ready = gameV == "ready", sub = NSMutableAttributedString(string: "●  ", attributes: [.foregroundColor: ready ? T.ok : T.warn, .font: NSFont.systemFont(ofSize: 10)])
        sub.append(NSAttributedString(string: ready ? "Native build ready · \(steam ? "Steam running" : "Steam not running")" : "Not built yet", attributes: [.foregroundColor: NSColor(white: 1, alpha: 0.75), .font: NSFont.systemFont(ofSize: 13)]))
        sub.addAttribute(.paragraphStyle, value: oneLine, range: NSRange(location: 0, length: sub.length)); heroSub.attributedStringValue = sub
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: support.appendingPathComponent("profiles").path)) ?? []).filter { !$0.hasPrefix(".") && !$0.hasSuffix(".txt") }.sorted()
        let current = profiles.titleOfSelectedItem
        for pop in [profiles] where Set(names.isEmpty ? ["Default"] : names) != Set(pop.itemTitles) {
            pop.removeAllItems(); pop.addItems(withTitles: names.isEmpty ? ["Default"] : names)
            let saved = UserDefaults.standard.string(forKey: "lc.profile")
            if let c = current, names.contains(c) { pop.selectItem(withTitle: c) }
            else if let c = saved, names.contains(c) { pop.selectItem(withTitle: c) }
            else if names.contains("Default") { pop.selectItem(withTitle: "Default") }
        }
        updateProfileButton(); syncProfileChips()
    }
    /// One status cell: bold value in `color`, then `short` (or the hint itself) as the one-line hint; the full hint is the tooltip.
    func set(_ key: String, _ value: String, _ hint: String, _ color: NSColor, short: String? = nil) {
        guard let r = statusRows[key] else { return }; r.0.stringValue = value; r.0.textColor = color
        let h = short ?? hint; r.1.stringValue = h.isEmpty ? "" : "· " + h
        for v in [statusCells[key], r.0, r.1].compactMap({ $0 }) { v.toolTip = hint.isEmpty ? nil : hint }
    }
    /// "2026-10-25 09:50" -> "built today" / "built yesterday" / "built Oct 25".
    func builtAgo(_ s: String) -> String {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd HH:mm"
        guard let d = f.date(from: s) else { return "built" }
        if Calendar.current.isDateInToday(d) { return "built today" }
        if Calendar.current.isDateInYesterday(d) { return "built yesterday" }
        let o = DateFormatter(); o.locale = Locale(identifier: "en_US"); o.dateFormat = Calendar.current.isDate(d, equalTo: Date(), toGranularity: .year) ? "MMM d" : "MMM d, yyyy"
        return "built " + o.string(from: d)
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
        var env = ProcessInfo.processInfo.environment; env["PATH"] = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:" + (env["PATH"] ?? ""); env["PYTHONUNBUFFERED"] = "1"; p.environment = env; return p
    }
    func run(_ args: [String], then: (() -> Void)? = nil) {
        if process != nil { appendLog("(busy: wait for the current task to finish)\n"); return }
        let p = makeProcess(args); let pipe = Pipe(); p.standardOutput = pipe; p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { h in
            let d = h.availableData; if d.isEmpty { return }
            DispatchQueue.main.async { self.feed(d) }  // control lines drive the status; everything else goes to the log
        }
        p.terminationHandler = { pr in
            DispatchQueue.main.async {
                pipe.fileHandleForReading.readabilityHandler = nil
                self.endTask(pr.terminationStatus)
                self.appendLog(pr.terminationStatus == 0 ? "\n" : "\n(exited with code \(pr.terminationStatus))\n")
                self.process = nil; self.modsBusy = false; self.setBusy(false); self.refreshStatus(); then?()
            }
        }
        appendLog("\n$ lcport " + args.joined(separator: " ") + "\n"); beginTask(args)
        do { try p.run(); process = p; modsBusy = args.first == "mods" && args.count > 1 && args[1] != "audit"; setBusy(true); if !drawerOpen && current != "activity" { setDrawer(true) } }
        catch { appendLog("could not start: \(error)\n"); _ = control("##fail Could not start the task, see Activity"); barVisible = false; renderTask() }
    }
    func kitJSON(_ args: [String], _ completion: @escaping (Any?) -> Void) {
        DispatchQueue.global().async {
            let p = self.makeProcess(args); let out = Pipe(); p.standardOutput = out; p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { DispatchQueue.main.async { completion(nil) }; return }
            let data = out.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
            let obj = try? JSONSerialization.jsonObject(with: data); DispatchQueue.main.async { completion(obj) }
        }
    }
    func setBusy(_ b: Bool) { b ? spinner.startAnimation(nil) : spinner.stopAnimation(nil); for x in buttons where x.title != "Clear" && x.title != "Quit" { x.isEnabled = !b }; refreshTiles() }
    func appendLog(_ s: String) {
        let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: T.text]
        log.textStorage?.append(NSAttributedString(string: s, attributes: attrs)); log.scrollToEndOfDocument(nil)
        activityLog.textStorage?.append(NSAttributedString(string: s, attributes: attrs)); activityLog.scrollToEndOfDocument(nil)
    }
    var profile: String { profiles.titleOfSelectedItem ?? "Default" }

    // MARK: actions
    @objc func play() { run(["play"]) }
    @objc func playModded() { run(["play-modded", profile]) }
    /// The hero's one Play button follows the Vanilla / Mods switch.
    @objc func playSelected() { modeSwitch.selected == 1 ? playModded() : play() }
    func setMode(_ mode: String) {
        let mods = mode == "mods"; UserDefaults.standard.set(mods ? "mods" : "vanilla", forKey: "lc.mode")
        if modeSwitch.selected != (mods ? 1 : 0) { modeSwitch.selected = mods ? 1 : 0 }
        profilesHome.isHidden = !mods; playButton.title = mods ? "▶  Play with mods" : "▶  Play"; playButton.refresh()
    }
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
    @objc func addToSteam() {
        run(["steam-shortcut"])  // its "##done" line carries the "restart Steam once" hint
    }
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
        UserDefaults.standard.set(profile, forKey: "lc.profile"); updateProfileButton()
        pendingInstall.removeAll(); pendingRemove.removeAll(); syncProfileChips()
        reloadInstalled { self.afterInstalledChange() }
    }
    /// Home's profile control: a pill titled "<name>  ▾" (chevron muted) that drops a menu of profiles plus New / Remove.
    func updateProfileButton() {
        profilesHome.title = profile + "  ▾"; profilesHome.refresh()
    }
    @objc func openProfileMenu() {
        let m = NSMenu(); m.autoenablesItems = false
        for n in profiles.itemTitles {
            let it = NSMenuItem(title: n, action: #selector(profileMenuPicked(_:)), keyEquivalent: ""); it.target = self; it.state = n == profile ? .on : .off; m.addItem(it)
        }
        m.addItem(.separator())
        let add = NSMenuItem(title: "New profile…", action: #selector(newProfile), keyEquivalent: ""); add.target = self; m.addItem(add)
        let rm = NSMenuItem(title: "Remove '\(profile)'…", action: #selector(removeProfile), keyEquivalent: ""); rm.target = self
        rm.isEnabled = profiles.numberOfItems > 1; m.addItem(rm)
        m.popUp(positioning: nil, at: NSPoint(x: 0, y: profilesHome.isFlipped ? profilesHome.bounds.height + 3 : -3), in: profilesHome)  // bottom-left of the button
    }
    @objc func profileMenuPicked(_ item: NSMenuItem) { guard item.title != profile else { return }; profiles.selectItem(withTitle: item.title); profileChanged() }
    @objc func removeProfile() {
        let name = profile, a = NSAlert(); a.alertStyle = .critical
        a.messageText = "Remove profile '\(name)'?"; a.informativeText = "Its mods are deleted from this Mac. Mod lists you imported can be imported again."
        a.addButton(withTitle: "Remove"); a.addButton(withTitle: "Cancel")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        run(["mods", "delete-profile", name]) {
            let rest = self.profiles.itemTitles.filter { $0 != name }
            UserDefaults.standard.set(rest.contains("Default") ? "Default" : (rest.first ?? "Default"), forKey: "lc.profile")
            self.refreshStatus()
            if let t = (rest.contains("Default") ? "Default" : rest.first) { self.profiles.selectItem(withTitle: t) }
            self.profileChanged()
        }
    }
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
        if snapshotSelect, let f = snapshotSheetMod() { snapshotSelect = false; openSheet(f) }
        if snapshotPending, !results.isEmpty { snapshotPending = false; injectPending() }
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
        let inst = installed[full], queued = pendingInstall.contains(full) || pendingRemove.contains(full)
        if queued { tile.state.stringValue = "● queued"; tile.state.textColor = T.accent }
        else if let v = inst { tile.state.stringValue = "● installed \(v)"; tile.state.textColor = T.ok }
        else { tile.state.stringValue = "" }
        tile.action.identifier = NSUserInterfaceItemIdentifier(full); tile.action.target = self; tile.action.action = #selector(tileAction(_:))
        styleAction(tile.action, full)
        tile.stripe.layer?.backgroundColor = verdict(full).0.cgColor
        tile.selected = selectedMod == full; tile.pending = queued
        tile.onClick = { [weak self] in self?.openSheet(full) }
        if tile.iconKey != full { tile.iconKey = full; tile.icon.image = IconCache.shared.cached(full) }
        if tile.icon.image == nil {
            IconCache.shared.image(full, url: r["icon"] as? String ?? "") { [weak tile] img in if let t = tile, t.iconKey == full { t.icon.image = img } }
        }
    }
    /// Install (primary) for a mod that is not installed, Remove (secondary) for an installed one, Undo (outline) while a change is queued.
    /// Disabled while a mods command runs, because its end clears the queue.
    func styleAction(_ b: FlatButton, _ full: String) {
        if pendingInstall.contains(full) || pendingRemove.contains(full) { b.title = "Undo"; b.setStyle(.outline) }
        else if installed[full] != nil { b.title = "Remove"; b.setStyle(.secondary) }
        else { b.title = "Install"; b.setStyle(.primary) }
        b.isEnabled = !modsBusy; b.invalidateIntrinsicContentSize()
    }
    @objc func tileAction(_ b: NSButton) { if let full = b.identifier?.rawValue { togglePending(full) } }
    /// Batch model: Install queues an install, Remove queues a remove, Undo clears the queued change. Apply runs the queue.
    func togglePending(_ full: String) {
        if pendingInstall.contains(full) { pendingInstall.remove(full) }
        else if pendingRemove.contains(full) { pendingRemove.remove(full) }
        else if installed[full] != nil { pendingRemove.insert(full) }
        else { pendingInstall.insert(full) }
        refreshTiles()
    }
    /// LC_SNAPSHOT_SELECT opens MoreCompany's sheet when it is listed, otherwise the first tile's.
    func snapshotSheetMod() -> String? {
        let names = results.compactMap { $0["full_name"] as? String }
        return names.contains("notnotnotswipez-MoreCompany") ? "notnotnotswipez-MoreCompany" : names.first
    }
    /// LC_SNAPSHOT_PENDING: queue the second installed and the second not-installed mod on screen, so every tile state shows.
    func injectPending() {
        let names = results.prefix(9).compactMap { $0["full_name"] as? String }
        let inst = names.filter { installed[$0] != nil }, other = names.filter { installed[$0] == nil }
        pendingRemove = Set((inst.count > 1 ? inst[1] : inst.first).map { [$0] } ?? [])
        pendingInstall = Set((other.count > 1 ? other[1] : other.first).map { [$0] } ?? [])
        refreshTiles()
    }
    /// Re-render visible tiles, the mod sheet and the apply bar in place (no reload, so scrolling and icons stay put).
    func refreshTiles() {
        guard grid != nil else { return }
        for ip in grid.indexPathsForVisibleItems() where ip.item < results.count { if let it = grid.item(at: ip) as? ModTileItem { configure(it.tile, results[ip.item]) } }
        updateApplyBar(); fillSheet()
    }
    func updateApplyBar() {
        if modsBusy {  // a mods command is running: the bar shows its status and progress instead of the pending counts
            var t = taskText; if let pc = taskPct, taskState == .busy { t += "  ·  \(Int(pc))%" }
            applyLabel.stringValue = t; applyProg.isHidden = false
            if let pc = taskPct { applyProg.isIndeterminate = false; applyProg.stopAnimation(nil); applyProg.doubleValue = pc } else { applyProg.isIndeterminate = true; applyProg.startAnimation(nil) }
            if applyBar.isHidden { applyBar.isHidden = false; bodyToPage.isActive = false; bodyToBar.isActive = true }
            return
        }
        applyProg.isHidden = true; applyProg.stopAnimation(nil)
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

    // mod sheet
    func record(_ full: String) -> [String: Any]? { results.first { $0["full_name"] as? String == full } ?? allResults.first { $0["full_name"] as? String == full } }
    func openSheet(_ full: String) {
        selectedMod = full; selectedRecord = record(full)
        if sheet.isHidden { sheet.isHidden = false; window.makeFirstResponder(sheet) }
        refreshTiles(); loadReadme(full)
        if infos[full] == nil {
            kitJSON(["mods", "json-info", full]) { obj in
                self.infos[full] = obj as? [String: Any] ?? ["error": "failed"]
                if self.selectedMod == full { self.fillSheet() }  // ignore results for a mod whose sheet is no longer open
            }
        }
    }
    @objc func closeSheet() {
        guard !sheet.isHidden else { return }
        sheet.isHidden = true; selectedMod = nil; selectedRecord = nil; readmeShown = nil; sNav = nil; refreshTiles()
    }
    /// Mac verdict as a chip: coloured dot plus a short label; the audit notes are its tooltip.
    func verdictChip(_ full: String) -> TagChip {
        let (color, headline, notes) = verdict(full)
        let text: String
        if installed[full] == nil { text = "Mac check after install" }
        else { switch audit[full]?["group"] as? String { case "auto": text = "visuals auto-fixed"; case "fix": text = "needs porting"; case "ok": text = "works on Mac"; default: text = "no audit issues" } }
        let c = TagChip(text, dot: color == T.line ? T.muted : color); c.toolTip = ([headline] + notes.map { "• " + $0 }).joined(separator: "\n"); return c
    }
    func fillSheet() {
        guard let full = selectedMod, !sheet.isHidden else { return }
        if selectedRecord == nil { selectedRecord = record(full) }
        let r = selectedRecord ?? ["full_name": full, "name": full]
        if sIconKey != full {
            sIconKey = full; sIcon.image = IconCache.shared.cached(full)
            if sIcon.image == nil { IconCache.shared.image(full, url: r["icon"] as? String ?? "") { img in if self.sIconKey == full { self.sIcon.image = img } } }
        }
        sName.stringValue = r["name"] as? String ?? ""
        let info = infos[full]
        var meta = "by \(r["owner"] as? String ?? "") · \(r["version"] as? String ?? "?") · \(fmtDownloads(r["downloads"] as? Int ?? 0)) downloads"
        let updated = (info?["date_updated"] as? String).map { String($0.prefix(10)) } ?? (readmes[full]?["updated"] as? String ?? "")
        if updated.count == 10 { meta += " · updated \(updated)" }
        sMeta.stringValue = meta
        var chips: [NSView] = [verdictChip(full)]
        chips += (r["categories"] as? [String] ?? []).map { TagChip($0) }
        for d in info?["dependencies"] as? [String] ?? [] {
            let n = splitRef(d).0; chips.append(TagChip("needs " + (n.split(separator: "-", maxSplits: 1).last.map(String.init) ?? n)))
        }
        sChips.views = chips
        styleAction(sAction, full)
        let inst = installed[full]
        if pendingInstall.contains(full) { sNote.stringValue = "Queued: installs when you apply changes"; sNote.textColor = T.accent }
        else if pendingRemove.contains(full) { sNote.stringValue = "Queued: removed when you apply changes"; sNote.textColor = T.accent }
        else if let v = inst { sNote.stringValue = "● installed \(v)"; sNote.textColor = T.ok }
        else { sNote.stringValue = "" }
        sFallbackDesc.stringValue = r["description"] as? String ?? ""
    }
    /// README from `mods json-readme` (the kit caches it on disk; successes are also kept in memory for this session).
    func loadReadme(_ full: String) {
        if readmeShown == full { return }
        readmeShown = full; sNav = nil; sWeb.isHidden = true; sFallback.isHidden = true; sLoading.isHidden = false
        if let d = readmes[full] { showReadme(full, d); return }
        kitJSON(["mods", "json-readme", full]) { obj in
            let d = obj as? [String: Any] ?? [:]
            if !(d["html"] as? String ?? "").isEmpty { self.readmes[full] = d }
            if self.readmeShown == full { self.showReadme(full, d); self.fillSheet() }
        }
    }
    func showReadme(_ full: String, _ d: [String: Any]) {
        let html = d["html"] as? String ?? ""
        if html.isEmpty { readmeFailed(); return }
        sNav = sWeb.loadHTMLString(html, baseURL: URL(string: "https://thunderstore.io/"))
    }
    func readmeFailed() { sNav = nil; sLoading.isHidden = true; sWeb.isHidden = true; sFallback.isHidden = false; readmeSettled() }
    /// LC_SNAPSHOT_SELECT: the picture is taken 4 s after the README settled, so its images have time to arrive.
    func readmeSettled() {
        guard let path = snapshotSheetPath else { return }
        snapshotSheetPath = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) { self.snapshot(to: path); NSApp.terminate(nil) }
    }
    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
        guard n != nil, n === sNav else { return }
        sLoading.isHidden = true; sWeb.isHidden = false; readmeSettled()
    }
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { if n != nil && n === sNav { readmeFailed() } }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { if n != nil && n === sNav { readmeFailed() } }
    /// Links in the README open in the default browser; only the README itself loads in the sheet.
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if a.navigationType == .linkActivated || a.targetFrame == nil, let u = a.request.url, ["http", "https", "mailto"].contains(u.scheme ?? "") {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(a.navigationType == .other ? .allow : .cancel)
    }
    /// "Author-Name-1.2.3" -> ("Author-Name", "1.2.3")
    func splitRef(_ ref: String) -> (String, String) {
        guard let i = ref.lastIndex(of: "-"), ref[ref.index(after: i)...].allSatisfy({ $0.isNumber || $0 == "." }) else { return (ref, "") }
        return (String(ref[..<i]), String(ref[ref.index(after: i)...]))
    }
    @objc func sheetAction() { if let f = selectedMod { togglePending(f) } }
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
