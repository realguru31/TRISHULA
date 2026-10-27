#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// TRISHULA signals + Book for NinjaTrader 8 (v5, 27 Oct 2026).
// v5: signal arrows + labels + status are painted in OnRender too (v4 drawing objects went missing after some reloads).
// v4: also draws the VS3D Book at ES prices — key levels (UP TEST / DN TEST / BALANCE: dashed = PREVIEW before the
// 09:35 ET lock, solid = LOCKED), the straddle band, and the dealer net-contracts profile per strike on the right edge.
// The Book is painted in OnRender (no drawing objects, no chart reload).
// Reads the TRISHULA JSON feed (https://trishula.streamlit.app/~/+/app/static/dtsignals_<KEY>.json) every N seconds in the
// background and draws the Signals-view marks (S1, S3–S7) on the chart at their ES level (SPX × ES/SPX ratio of that
// minute) or at the bar's high / low. Filters: sensitivity, tape (0DTE / 0+1DTE), each signal on/off, only signals that
// passed the walk-forward test. Read-only: it never sends anything.
// enums in the GLOBAL namespace: NinjaTrader's generated code (Market Analyzer / Strategy wrappers at the bottom of the
// file) refers to them without a namespace
public enum TrishulaSensitivity { Fewer, Middle, More }
public enum TrishulaTape { ZeroDTE, ZeroPlusOneDTE }

namespace NinjaTrader.NinjaScript.Indicators
{
    public class TrishulaSignals : Indicator
    {
        private class Mark
        {
            public string Id, Code, Name, Mode, Position, Session;
            public DateTime TimeEt;          // ET wall clock of the signal minute
            public int Dir;
            public bool Passed, RthPassed;
            public double Spx = double.NaN, Es = double.NaN;
        }

        private class BookLevel { public string Name, Kind; public double Spx = double.NaN, Es = double.NaN; }
        private class ProfBar { public double Strike, Es = double.NaN, Net, Conf; }
        private class BookData
        {
            public string State = "none", LockedAt = "";
            public double Ratio = double.NaN, StraddleValue = double.NaN, StraddleUpEs = double.NaN, StraddleDnEs = double.NaN;
            public List<BookLevel> Levels = new List<BookLevel>();
            public List<ProfBar> Profile = new List<ProfBar>();
        }
        private volatile BookData book;

        private System.Threading.Timer timer;
        private volatile List<Mark> latest = new List<Mark>();
        private volatile string feedGenerated = "", feedStatus = "", feedNote = "", lastError = "";
        private DateTime lastFetchLocal = DateTime.MinValue;
        private int busy;
        private static readonly TimeZoneInfo EasternTz = FindEastern();

        private static TimeZoneInfo FindEastern()
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
            catch { return TimeZoneInfo.Local; }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "TRISHULA Signals-view marks from the TRISHULA JSON feed (read-only).";
                Name = "TrishulaSignals";
                Calculate = Calculate.OnPriceChange;          // repaints on every price change → the feed shows up on the next tick
                IsOverlay = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;
                FeedUrl = "https://trishula.streamlit.app/~/+/app/static/dtsignals_12345678901234567890.json";
                PollSeconds = 30;
                Sensitivity = TrishulaSensitivity.More;
                Tape = TrishulaTape.ZeroPlusOneDTE;
                OnlyPassed = true;
                IncludeOvernight = true;
                OvernightBullBrush = Brushes.Aquamarine;
                OvernightBearBrush = Brushes.Orchid;
                ShowS1 = true; ShowS3 = true; ShowS4 = true; ShowS5 = true; ShowS6 = true; ShowS7 = true;
                PlaceAtEsLevel = true;
                OffsetTicks = 4;
                LabelPixels = 16;
                ArrowSize = 14;
                BullBrush = Brushes.LimeGreen;
                BearBrush = Brushes.HotPink;
                UnprovenBrush = Brushes.Gray;
                ShowStatusText = true;
                ShowLevels = true;
                ShowStraddle = true;
                ShowProfile = true;
                ProfileWidth = 220;
                ProfileOpacity = 70;
                ShowProfileNumbers = true;
                LineWidth = 2;
                UpTestBrush = Brushes.LimeGreen;
                DnTestBrush = Brushes.Tomato;
                BalanceBrush = Brushes.WhiteSmoke;
                StraddleBrush = Brushes.MediumPurple;
                ProfilePlusBrush = Brushes.LightSeaGreen;
                ProfileMinusBrush = Brushes.IndianRed;
            }
            else if (State == State.DataLoaded)
            {
                try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12; } catch { }
                int ms = Math.Max(10, PollSeconds) * 1000;
                timer = new System.Threading.Timer(_ => Poll(), null, 1000, ms);
            }
            else if (State == State.Terminated)
            {
                if (timer != null) { timer.Dispose(); timer = null; }
            }
        }

        // chart label shows just the name — never the feed URL / key (NinjaTrader otherwise prints every parameter)
        public override string DisplayName
        {
            get { return "TRISHULA"; }
        }

        protected override void OnBarUpdate()
        {
            // v5: nothing here — everything is painted in OnRender
        }

        // ── background: download + parse ─────────────────────────────────────────────────────────
        private void Poll()
        {
            if (Interlocked.Exchange(ref busy, 1) == 1) return;
            try
            {
                string json;
                using (var wc = new WebClient())
                {
                    wc.Headers[HttpRequestHeader.CacheControl] = "no-cache";
                    string sep = FeedUrl.Contains("?") ? "&" : "?";
                    json = wc.DownloadString(FeedUrl + sep + "t=" + DateTime.UtcNow.Ticks);
                }
                feedGenerated = Str(json, "generated");
                feedStatus = Str(json, "status");
                feedNote = Str(json, "note");
                latest = ParseMarks(json);
                book = ParseBook(json);
                lastError = "";
                lastFetchLocal = DateTime.Now;
            }
            catch (Exception ex)
            {
                lastError = ex.Message.Length > 120 ? ex.Message.Substring(0, 120) : ex.Message;
            }
            finally
            {
                Interlocked.Exchange(ref busy, 0);
            }
        }

        private static string Str(string json, string key)
        {
            var m = Regex.Match(json, "\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
            return m.Success ? m.Groups[1].Value : "";
        }

        private static List<Mark> ParseMarks(string json)
        {
            var list = new List<Mark>();
            int i = json.IndexOf("\"marks\"", StringComparison.Ordinal);
            if (i < 0) return list;
            int a = json.IndexOf('[', i), b = json.IndexOf(']', a);
            if (a < 0 || b < 0) return list;
            string arr = json.Substring(a + 1, b - a - 1);
            foreach (Match m in Regex.Matches(arr, "\\{[^{}]*\\}"))
            {
                string o = m.Value;
                var mk = new Mark
                {
                    Id = Str(o, "id"), Code = Str(o, "code"), Name = Str(o, "name"),
                    Mode = Str(o, "mode"), Position = Str(o, "position"), Session = Str(o, "session"),
                    Dir = (int)Num(o, "dir", 0), Passed = Regex.IsMatch(o, "\"passed\"\\s*:\\s*true"),
                    RthPassed = Regex.IsMatch(o, "\"rth_passed\"\\s*:\\s*true"),
                    Spx = Num(o, "spx", double.NaN), Es = Num(o, "es", double.NaN)
                };
                DateTimeOffset dto;
                if (!DateTimeOffset.TryParse(Str(o, "t"), CultureInfo.InvariantCulture, DateTimeStyles.None, out dto)) continue;
                mk.TimeEt = dto.DateTime;                       // the feed's wall clock is ET (offset -04:00 / -05:00)
                list.Add(mk);
            }
            return list;
        }

        // the "book" object: {"state":..,"locked_at":..,"ratio":..,"levels":[{..}],"straddle":{..}|null,"profile":[{..}]}
        private static BookData ParseBook(string json)
        {
            int i = json.IndexOf("\"book\"", StringComparison.Ordinal);
            if (i < 0) return null;
            int c = json.IndexOf(':', i);
            if (c < 0 || Regex.IsMatch(json.Substring(c + 1, Math.Min(8, json.Length - c - 1)), "^\\s*null")) return null;
            string b = json.Substring(c + 1);
            var bk = new BookData { State = Str(b, "state"), LockedAt = Str(b, "locked_at"), Ratio = Num(b, "ratio", double.NaN) };
            foreach (Match m in Regex.Matches(Arr(b, "levels"), "\\{[^{}]*\\}"))
                bk.Levels.Add(new BookLevel { Name = Str(m.Value, "name"), Kind = Str(m.Value, "kind"),
                                          Spx = Num(m.Value, "spx", double.NaN), Es = Num(m.Value, "es", double.NaN) });
            foreach (Match m in Regex.Matches(Arr(b, "profile"), "\\{[^{}]*\\}"))
            {
                var r = new ProfBar { Strike = Num(m.Value, "strike", double.NaN), Es = Num(m.Value, "es", double.NaN),
                                  Net = Num(m.Value, "net", 0), Conf = Num(m.Value, "conf", 0.5) };
                if (!double.IsNaN(r.Es) && r.Net != 0) bk.Profile.Add(r);
            }
            var sm = Regex.Match(b, "\"straddle\"\\s*:\\s*(\\{[^{}]*\\})");
            if (sm.Success)
            {
                bk.StraddleValue = Num(sm.Groups[1].Value, "value", double.NaN);
                bk.StraddleUpEs = Num(sm.Groups[1].Value, "up_es", double.NaN);
                bk.StraddleDnEs = Num(sm.Groups[1].Value, "dn_es", double.NaN);
            }
            return bk;
        }

        private static string Arr(string json, string key)
        {
            int i = json.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
            if (i < 0) return "";
            int a = json.IndexOf('[', i);
            if (a < 0) return "";
            int b = json.IndexOf(']', a);
            return b < 0 ? "" : json.Substring(a + 1, b - a - 1);
        }

        private static double Num(string o, string key, double dflt)
        {
            var m = Regex.Match(o, "\"" + key + "\"\\s*:\\s*(-?[0-9.]+)");
            double v;
            return m.Success && double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : dflt;
        }

        // ── chart thread: filter + draw ─────────────────────────────────────────────────────────
        private bool Wanted(Mark m)
        {
            string pos = Sensitivity == TrishulaSensitivity.Fewer ? "fewer" : Sensitivity == TrishulaSensitivity.Middle ? "middle" : "more";
            string mode = Tape == TrishulaTape.ZeroDTE ? "0DTE" : "0+1DTE";
            if (m.Position != pos || m.Mode != mode) return false;
            bool overnight = m.Session == "GTH";
            if (overnight && !IncludeOvernight) return false;
            // overnight marks are untested: with "only passed" ON, show overnight marks only for signals that passed in RTH
            if (OnlyPassed && !(overnight ? m.RthPassed : m.Passed)) return false;
            switch (m.Code)
            {
                case "S1": return ShowS1;
                case "S3": return ShowS3;
                case "S4": return ShowS4;
                case "S5": return ShowS5;
                case "S6": return ShowS6;
                case "S7": return ShowS7;
                default: return false;
            }
        }

        private DateTime ToChartTime(DateTime et)
        {
            // ET wall clock → the time zone NinjaTrader uses for bar times (Tools > Options > General > Time zone)
            try
            {
                var utc = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(et, DateTimeKind.Unspecified), EasternTz);
                return TimeZoneInfo.ConvertTimeFromUtc(utc, Core.Globals.GeneralOptions.TimeZoneInfo);
            }
            catch { return et; }
        }

        // v5: marks + status are PAINTED in OnRender every repaint (no drawing objects, no "already drawn" memory) —
        // if a mark is in the feed and passes the filters it is on the chart, every time, pinned to its bar and price.
        private string StatusText()
        {
            string age = "";
            DateTimeOffset g;
            if (DateTimeOffset.TryParse(feedGenerated, CultureInfo.InvariantCulture, DateTimeStyles.None, out g))
            {
                double mins = (DateTimeOffset.Now - g).TotalMinutes;
                age = mins > 3 && feedStatus == "live" ? "  ⚠ STALE " + mins.ToString("0") + " min" : "";
            }
            var last = latest.Where(Wanted).OrderBy(x => x.TimeEt).LastOrDefault();
            return "TRISHULA · " + (IncludeOvernight ? "RTH+ON · " : "RTH · ") + Sensitivity + " · " + (Tape == TrishulaTape.ZeroDTE ? "0DTE" : "0+1DTE")
                   + (OnlyPassed ? " · passed only" : " · all") + " · feed " + (feedStatus == "" ? "—" : feedStatus) + " "
                   + (feedGenerated.Length >= 19 ? feedGenerated.Substring(11, 8) : "") + " ET" + age
                   + BookStatus()
                   + (lastError != "" ? "\nERROR: " + lastError : "")
                   + (feedNote != "" ? "\n" + feedNote : "")
                   + (last != null ? "\nlast: " + last.Code + " " + (last.Dir > 0 ? "▲" : "▼") + " " + last.TimeEt.ToString("HH:mm") + " ET"
                                     + (double.IsNaN(last.Es) ? "" : " · ES " + last.Es.ToString("0.00")) : "");
        }

        private void RenderMarks(ChartControl chartControl, ChartScale chartScale, float top, float bottom)
        {
            if (Bars == null || Bars.Count == 0 || ChartBars == null) return;
            int from = Math.Max(0, ChartBars.FromIndex), to = Math.Min(Bars.Count - 1, ChartBars.ToIndex);
            using (var af = new SharpDX.DirectWrite.TextFormat(Core.Globals.DirectWriteFactory, "Arial", (float)ArrowSize))
            using (var lf = new SharpDX.DirectWrite.TextFormat(Core.Globals.DirectWriteFactory, "Arial", 9f))
            {
                af.TextAlignment = SharpDX.DirectWrite.TextAlignment.Center;
                af.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center;
                af.WordWrapping = SharpDX.DirectWrite.WordWrapping.NoWrap;
                lf.TextAlignment = SharpDX.DirectWrite.TextAlignment.Center;
                lf.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center;
                lf.WordWrapping = SharpDX.DirectWrite.WordWrapping.NoWrap;
                foreach (var m in latest)
                {
                    if (!Wanted(m)) continue;
                    int idx = Bars.GetBar(ToChartTime(m.TimeEt).AddMinutes(1));   // known at the END of its minute
                    if (idx < from || idx > to) continue;
                    bool up = m.Dir > 0;
                    double off = OffsetTicks * TickSize;
                    double price = PlaceAtEsLevel && !double.IsNaN(m.Es) ? (up ? m.Es - off : m.Es + off)
                                                                         : (up ? Bars.GetLow(idx) - off : Bars.GetHigh(idx) + off);
                    float x = chartControl.GetXByBarIndex(ChartBars, idx);
                    float y = chartScale.GetYByValue(price);
                    if (y < top - 40 || y > bottom + 40) continue;
                    bool overnight = m.Session == "GTH";
                    bool solid = overnight ? m.RthPassed : m.Passed;
                    Brush b = !solid ? UnprovenBrush : overnight ? (up ? OvernightBullBrush : OvernightBearBrush) : (up ? BullBrush : BearBrush);
                    float a = ArrowSize;
                    using (var br = Dx(b, 1f))
                    {
                        RenderTarget.DrawText(up ? "▲" : "▼", af, new SharpDX.RectangleF(x - a, y - a, 2 * a, 2 * a), br);
                        float ly = up ? y + LabelPixels : y - LabelPixels;     // label below an up arrow, above a down arrow
                        RenderTarget.DrawText(overnight ? m.Code + " ON" : m.Code, lf, new SharpDX.RectangleF(x - 30, ly - 7, 60, 14), br);
                    }
                }
            }
        }

        private string BookStatus()
        {
            var bk = book;
            if (bk == null) return "\nbook: —";
            if (bk.State == "locked")
                return "\nbook: LOCKED " + bk.LockedAt + " ET (solid)";
            if (bk.State == "preview") return "\nbook: PREVIEW — yesterday's book · locks 09:35 ET (dashed)";
            return "\nbook: no levels yet";
        }

        // ── the Book, painted every render (UI thread). Nothing here touches drawing objects or reloads the chart. ──
        private SharpDX.Direct2D1.SolidColorBrush Dx(Brush b, float opacity)
        {
            var c = (b as SolidColorBrush) != null ? ((SolidColorBrush)b).Color : Colors.Gray;
            return new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, Math.Max(0f, Math.Min(1f, opacity * c.A / 255f))));
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            var bk = book;
            if (RenderTarget == null || ChartPanel == null) return;
            float left = ChartPanel.X, right = ChartPanel.X + ChartPanel.W, top = ChartPanel.Y, bottom = ChartPanel.Y + ChartPanel.H;
            var oldAa = RenderTarget.AntialiasMode;
            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;
            if (bk != null)
            using (var tf = new SharpDX.DirectWrite.TextFormat(Core.Globals.DirectWriteFactory, "Arial", 11f))
            using (var tfs = new SharpDX.DirectWrite.TextFormat(Core.Globals.DirectWriteFactory, "Arial", 9f))
            using (var dash = new SharpDX.Direct2D1.StrokeStyle(Core.Globals.D2DFactory,
                       new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash }))
            using (var dot = new SharpDX.Direct2D1.StrokeStyle(Core.Globals.D2DFactory,
                       new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dot }))
            {
                tf.WordWrapping = SharpDX.DirectWrite.WordWrapping.NoWrap;
                tfs.WordWrapping = SharpDX.DirectWrite.WordWrapping.NoWrap;
                tfs.TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing;
                tfs.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center;
                tf.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Far;

                // 1) profile: dealer NET CONTRACTS per strike, bars grow leftwards from the right edge
                if (ShowProfile && bk.Profile.Count > 0)
                {
                    double maxAbs = bk.Profile.Max(r => Math.Abs(r.Net));
                    double step = double.IsNaN(bk.Ratio) ? 5.0 : 5.0 * bk.Ratio;      // SPX strikes are 5 apart
                    float h = Math.Max(1f, Math.Abs(chartScale.GetYByValue(bk.Profile[0].Es) - chartScale.GetYByValue(bk.Profile[0].Es + step)) * 0.8f);
                    foreach (var r in bk.Profile)
                    {
                        float y = chartScale.GetYByValue(r.Es);
                        if (y < top - h || y > bottom + h || maxAbs <= 0) continue;
                        float w = (float)(Math.Abs(r.Net) / maxAbs * ProfileWidth);
                        float op = (float)((0.35 + 0.6 * Math.Min(1.0, r.Conf)) * ProfileOpacity / 100.0);
                        using (var br = Dx(r.Net >= 0 ? ProfilePlusBrush : ProfileMinusBrush, op))
                            RenderTarget.FillRectangle(new SharpDX.RectangleF(right - w, y - h / 2f, w, h), br);
                        if (ShowProfileNumbers && h >= 9f)
                            using (var tb = Dx(Brushes.Gainsboro, 0.9f))
                                RenderTarget.DrawText(FmtK(r.Net) + "  " + r.Strike.ToString("0"), tfs,
                                    new SharpDX.RectangleF(right - ProfileWidth - 130, y - 8, 125, 16), tb);
                    }
                }

                // 2) straddle band (moves with spot)
                if (ShowStraddle && !double.IsNaN(bk.StraddleUpEs) && !double.IsNaN(bk.StraddleDnEs))
                    using (var sb = Dx(StraddleBrush, 0.9f))
                        foreach (var yv in new[] { bk.StraddleUpEs, bk.StraddleDnEs })
                        {
                            float y = chartScale.GetYByValue(yv);
                            if (y < top || y > bottom) continue;
                            RenderTarget.DrawLine(new SharpDX.Vector2(left, y), new SharpDX.Vector2(right, y), sb, 1f, dot);
                            RenderTarget.DrawText((yv > bk.StraddleDnEs ? "STRADDLE +" : "STRADDLE −") + bk.StraddleValue.ToString("0.0")
                                + "  " + yv.ToString("0.00"), tf, new SharpDX.RectangleF(left + 4, y - 16, 300, 15), sb);
                        }

                // 3) key levels: dashed = PREVIEW (before 09:35 ET), solid = LOCKED
                if (ShowLevels && bk.Levels.Count > 0)
                {
                    bool locked = bk.State == "locked";
                    foreach (var lv in bk.Levels)
                    {
                        if (double.IsNaN(lv.Es)) continue;
                        float y = chartScale.GetYByValue(lv.Es);
                        if (y < top || y > bottom) continue;
                        Brush b = lv.Kind == "up" ? UpTestBrush : lv.Kind == "dn" ? DnTestBrush : BalanceBrush;
                        using (var lb = Dx(b, locked ? 1f : 0.75f))
                        {
                            if (locked) RenderTarget.DrawLine(new SharpDX.Vector2(left, y), new SharpDX.Vector2(right, y), lb, LineWidth);
                            else RenderTarget.DrawLine(new SharpDX.Vector2(left, y), new SharpDX.Vector2(right, y), lb, LineWidth, dash);
                            RenderTarget.DrawText(lv.Name + (locked ? "" : " (preview)") + "  " + lv.Es.ToString("0.00")
                                + "  · SPX " + lv.Spx.ToString("0"), tf, new SharpDX.RectangleF(left + 4, y - 16, 400, 15), lb);
                        }
                    }
                }
            }
            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.PerPrimitive;
            RenderMarks(chartControl, chartScale, top, bottom);
            if (ShowStatusText)
                using (var sf = new SharpDX.DirectWrite.TextFormat(Core.Globals.DirectWriteFactory, "Arial", 12f))
                using (var sb = Dx(Brushes.Gainsboro, 1f))
                {
                    sf.WordWrapping = SharpDX.DirectWrite.WordWrapping.NoWrap;
                    RenderTarget.DrawText(StatusText(), sf, new SharpDX.RectangleF(left + 8, top + 18, 900, 90), sb);
                }
            RenderTarget.AntialiasMode = oldAa;
        }

        private static string FmtK(double v)
        {
            string s = v >= 0 ? "+" : "−";
            double a = Math.Abs(v);
            return s + (a >= 1000 ? (a / 1000).ToString("0.0") + "k" : a.ToString("0"));
        }

        #region Properties
        [NinjaScriptProperty, Display(Name = "Feed URL", Order = 1, GroupName = "1. Feed")]
        public string FeedUrl { get; set; }

        [NinjaScriptProperty, Range(10, 600), Display(Name = "Poll every (seconds)", Order = 2, GroupName = "1. Feed")]
        public int PollSeconds { get; set; }

        [NinjaScriptProperty, Display(Name = "Sensitivity", Order = 1, GroupName = "2. Signals")]
        public TrishulaSensitivity Sensitivity { get; set; }

        [NinjaScriptProperty, Display(Name = "Tape", Order = 2, GroupName = "2. Signals")]
        public TrishulaTape Tape { get; set; }

        [NinjaScriptProperty, Display(Name = "Only signals that passed the test", Order = 3, GroupName = "2. Signals")]
        public bool OnlyPassed { get; set; }

        [NinjaScriptProperty, Display(Name = "Include overnight (GTH, untested)", Order = 10, GroupName = "2. Signals")]
        public bool IncludeOvernight { get; set; }

        [NinjaScriptProperty, Display(Name = "S1 aggressive block vs move", Order = 4, GroupName = "2. Signals")]
        public bool ShowS1 { get; set; }
        [NinjaScriptProperty, Display(Name = "S3 near-spot flip", Order = 5, GroupName = "2. Signals")]
        public bool ShowS3 { get; set; }
        [NinjaScriptProperty, Display(Name = "S4 DT v2 follow", Order = 6, GroupName = "2. Signals")]
        public bool ShowS4 { get; set; }
        [NinjaScriptProperty, Display(Name = "S5 initiation", Order = 7, GroupName = "2. Signals")]
        public bool ShowS5 { get; set; }
        [NinjaScriptProperty, Display(Name = "S6 exhaustion + breadth", Order = 8, GroupName = "2. Signals")]
        public bool ShowS6 { get; set; }
        [NinjaScriptProperty, Display(Name = "S7 quiet big block", Order = 9, GroupName = "2. Signals")]
        public bool ShowS7 { get; set; }

        [NinjaScriptProperty, Display(Name = "Place at ES level (else bar high/low)", Order = 1, GroupName = "3. Display")]
        public bool PlaceAtEsLevel { get; set; }

        [NinjaScriptProperty, Range(0, 100), Display(Name = "Offset (ticks)", Order = 2, GroupName = "3. Display")]
        public int OffsetTicks { get; set; }

        [NinjaScriptProperty, Range(0, 100), Display(Name = "Label distance from arrow (pixels)", Order = 3, GroupName = "3. Display")]
        public int LabelPixels { get; set; }

        [NinjaScriptProperty, Range(6, 40), Display(Name = "Arrow size", Order = 4, GroupName = "3. Display")]
        public int ArrowSize { get; set; }

        [NinjaScriptProperty, Display(Name = "Status text", Order = 3, GroupName = "3. Display")]
        public bool ShowStatusText { get; set; }

        [XmlIgnore, Display(Name = "Bullish colour", Order = 4, GroupName = "3. Display")]
        public Brush BullBrush { get; set; }
        [Browsable(false)]
        public string BullBrushSerializable { get { return Serialize.BrushToString(BullBrush); } set { BullBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Bearish colour", Order = 5, GroupName = "3. Display")]
        public Brush BearBrush { get; set; }
        [Browsable(false)]
        public string BearBrushSerializable { get { return Serialize.BrushToString(BearBrush); } set { BearBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Overnight bullish colour", Order = 7, GroupName = "3. Display")]
        public Brush OvernightBullBrush { get; set; }
        [Browsable(false)]
        public string OvernightBullBrushSerializable { get { return Serialize.BrushToString(OvernightBullBrush); } set { OvernightBullBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Overnight bearish colour", Order = 8, GroupName = "3. Display")]
        public Brush OvernightBearBrush { get; set; }
        [Browsable(false)]
        public string OvernightBearBrushSerializable { get { return Serialize.BrushToString(OvernightBearBrush); } set { OvernightBearBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Unproven colour", Order = 6, GroupName = "3. Display")]
        public Brush UnprovenBrush { get; set; }
        [Browsable(false)]
        public string UnprovenBrushSerializable { get { return Serialize.BrushToString(UnprovenBrush); } set { UnprovenBrush = Serialize.StringToBrush(value); } }

        [NinjaScriptProperty, Display(Name = "Key levels (UP / DN TEST, BALANCE)", Order = 1, GroupName = "4. Book")]
        public bool ShowLevels { get; set; }
        [NinjaScriptProperty, Display(Name = "Straddle band", Order = 2, GroupName = "4. Book")]
        public bool ShowStraddle { get; set; }
        [NinjaScriptProperty, Display(Name = "Profile (dealer net contracts per strike)", Order = 3, GroupName = "4. Book")]
        public bool ShowProfile { get; set; }
        [NinjaScriptProperty, Range(20, 1000), Display(Name = "Profile width (pixels)", Order = 4, GroupName = "4. Book")]
        public int ProfileWidth { get; set; }
        [NinjaScriptProperty, Range(5, 100), Display(Name = "Profile opacity (%)", Order = 5, GroupName = "4. Book")]
        public int ProfileOpacity { get; set; }
        [NinjaScriptProperty, Display(Name = "Profile numbers (contracts · SPX strike)", Order = 6, GroupName = "4. Book")]
        public bool ShowProfileNumbers { get; set; }
        [NinjaScriptProperty, Range(1, 6), Display(Name = "Level line width", Order = 7, GroupName = "4. Book")]
        public int LineWidth { get; set; }

        [XmlIgnore, Display(Name = "UP TEST colour", Order = 10, GroupName = "4. Book")]
        public Brush UpTestBrush { get; set; }
        [Browsable(false)]
        public string UpTestBrushSerializable { get { return Serialize.BrushToString(UpTestBrush); } set { UpTestBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "DN TEST colour", Order = 11, GroupName = "4. Book")]
        public Brush DnTestBrush { get; set; }
        [Browsable(false)]
        public string DnTestBrushSerializable { get { return Serialize.BrushToString(DnTestBrush); } set { DnTestBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "BALANCE colour", Order = 12, GroupName = "4. Book")]
        public Brush BalanceBrush { get; set; }
        [Browsable(false)]
        public string BalanceBrushSerializable { get { return Serialize.BrushToString(BalanceBrush); } set { BalanceBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Straddle colour", Order = 13, GroupName = "4. Book")]
        public Brush StraddleBrush { get; set; }
        [Browsable(false)]
        public string StraddleBrushSerializable { get { return Serialize.BrushToString(StraddleBrush); } set { StraddleBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Profile + (dealer long) colour", Order = 14, GroupName = "4. Book")]
        public Brush ProfilePlusBrush { get; set; }
        [Browsable(false)]
        public string ProfilePlusBrushSerializable { get { return Serialize.BrushToString(ProfilePlusBrush); } set { ProfilePlusBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore, Display(Name = "Profile − (dealer short) colour", Order = 15, GroupName = "4. Book")]
        public Brush ProfileMinusBrush { get; set; }
        [Browsable(false)]
        public string ProfileMinusBrushSerializable { get { return Serialize.BrushToString(ProfileMinusBrush); } set { ProfileMinusBrush = Serialize.StringToBrush(value); } }
        #endregion
    }
}
