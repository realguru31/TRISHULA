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
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// TRISHULA signals for NinjaTrader 8 (v1, 27 Oct 2026).
// Reads the TRISHULA JSON feed (https://trishula.streamlit.app/app/static/dtsignals_<KEY>.json) every N seconds in the
// background and draws the Signals-view marks (S1, S3–S7) on the chart at their ES level (SPX × ES/SPX ratio of that
// minute) or at the bar's high / low. Filters: sensitivity, tape (0DTE / 0+1DTE), each signal on/off, only signals that
// passed the walk-forward test. Read-only: it never sends anything.
namespace NinjaTrader.NinjaScript.Indicators
{
    public enum TrishulaSensitivity { Fewer, Middle, More }
    public enum TrishulaTape { ZeroDTE, ZeroPlusOneDTE }

    public class TrishulaSignals : Indicator
    {
        private class Mark
        {
            public string Id, Code, Name, Mode, Position;
            public DateTime TimeEt;          // ET wall clock of the signal minute
            public int Dir;
            public bool Passed;
            public double Spx = double.NaN, Es = double.NaN;
        }

        private Timer timer;
        private volatile List<Mark> latest = new List<Mark>();
        private volatile string feedGenerated = "", feedStatus = "", feedNote = "", lastError = "";
        private DateTime lastFetchLocal = DateTime.MinValue;
        private readonly HashSet<string> drawn = new HashSet<string>();
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
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;
                FeedUrl = "https://trishula.streamlit.app/app/static/dtsignals_YOURKEY.json";
                PollSeconds = 30;
                Sensitivity = TrishulaSensitivity.More;
                Tape = TrishulaTape.ZeroPlusOneDTE;
                OnlyPassed = true;
                ShowS1 = true; ShowS3 = true; ShowS4 = true; ShowS5 = true; ShowS6 = true; ShowS7 = true;
                PlaceAtEsLevel = true;
                OffsetTicks = 6;
                BullBrush = Brushes.LimeGreen;
                BearBrush = Brushes.HotPink;
                UnprovenBrush = Brushes.Gray;
                ShowStatusText = true;
            }
            else if (State == State.DataLoaded)
            {
                try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12; } catch { }
                int ms = Math.Max(10, PollSeconds) * 1000;
                timer = new Timer(_ => Poll(), null, 1000, ms);
            }
            else if (State == State.Terminated)
            {
                if (timer != null) { timer.Dispose(); timer = null; }
            }
        }

        protected override void OnBarUpdate()
        {
            // drawing happens when new feed data arrives (TriggerCustomEvent in Poll); nothing per bar
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
            try { TriggerCustomEvent(o => Redraw(), null); } catch { }
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
                    Mode = Str(o, "mode"), Position = Str(o, "position"),
                    Dir = (int)Num(o, "dir", 0), Passed = Regex.IsMatch(o, "\"passed\"\\s*:\\s*true"),
                    Spx = Num(o, "spx", double.NaN), Es = Num(o, "es", double.NaN)
                };
                DateTimeOffset dto;
                if (!DateTimeOffset.TryParse(Str(o, "t"), CultureInfo.InvariantCulture, DateTimeStyles.None, out dto)) continue;
                mk.TimeEt = dto.DateTime;                       // the feed's wall clock is ET (offset -04:00 / -05:00)
                list.Add(mk);
            }
            return list;
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
            if (OnlyPassed && !m.Passed) return false;
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

        private void Redraw()
        {
            if (Bars == null || Bars.Count == 0) return;
            var keep = new HashSet<string>();
            foreach (var m in latest)
            {
                if (!Wanted(m)) continue;
                DateTime t = ToChartTime(m.TimeEt).AddMinutes(1);   // the signal is known at the END of its minute
                int idx = Bars.GetBar(t);
                if (idx < 0 || idx >= Bars.Count) continue;
                DateTime barTime = Bars.GetTime(idx);
                bool up = m.Dir > 0;
                double off = OffsetTicks * TickSize;
                double y;
                if (PlaceAtEsLevel && !double.IsNaN(m.Es))
                    y = up ? m.Es - off : m.Es + off;
                else
                    y = up ? Bars.GetLow(idx) - off : Bars.GetHigh(idx) + off;
                Brush br = !m.Passed ? UnprovenBrush : (up ? BullBrush : BearBrush);
                string tag = "TRI_" + m.Id;
                keep.Add(tag);
                if (up) Draw.ArrowUp(this, tag, false, barTime, y, br);
                else Draw.ArrowDown(this, tag, false, barTime, y, br);
                Draw.Text(this, tag + "_t", false, m.Code, barTime, up ? y - 2 * off : y + 2 * off, 0, br,
                          new SimpleFont("Arial", 9), System.Windows.TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
                keep.Add(tag + "_t");
            }
            foreach (var old in drawn.Where(x => !keep.Contains(x)).ToList())
                RemoveDrawObject(old);
            drawn.Clear();
            foreach (var k in keep) drawn.Add(k);

            if (ShowStatusText)
            {
                string age = "";
                DateTimeOffset g;
                if (DateTimeOffset.TryParse(feedGenerated, CultureInfo.InvariantCulture, DateTimeStyles.None, out g))
                {
                    double mins = (DateTimeOffset.Now - g).TotalMinutes;
                    age = mins > 3 && feedStatus == "live" ? "  ⚠ STALE " + mins.ToString("0") + " min" : "";
                }
                var last = latest.Where(Wanted).OrderBy(x => x.TimeEt).LastOrDefault();
                string txt = "TRISHULA · " + Sensitivity + " · " + (Tape == TrishulaTape.ZeroDTE ? "0DTE" : "0+1DTE")
                             + " · feed " + (feedStatus == "" ? "—" : feedStatus) + " " + (feedGenerated.Length >= 19 ? feedGenerated.Substring(11, 8) : "") + " ET" + age
                             + (lastError != "" ? "\nERROR: " + lastError : "")
                             + (feedNote != "" ? "\n" + feedNote : "")
                             + (last != null ? "\nlast: " + last.Code + " " + (last.Dir > 0 ? "▲" : "▼") + " " + last.TimeEt.ToString("HH:mm") + " ET"
                                               + (double.IsNaN(last.Es) ? "" : " · ES " + last.Es.ToString("0.00")) : "");
                Draw.TextFixed(this, "TRI_status", txt, TextPosition.TopLeft);
            }
            ForceRefresh();
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

        [XmlIgnore, Display(Name = "Unproven colour", Order = 6, GroupName = "3. Display")]
        public Brush UnprovenBrush { get; set; }
        [Browsable(false)]
        public string UnprovenBrushSerializable { get { return Serialize.BrushToString(UnprovenBrush); } set { UnprovenBrush = Serialize.StringToBrush(value); } }
        #endregion
    }
}
