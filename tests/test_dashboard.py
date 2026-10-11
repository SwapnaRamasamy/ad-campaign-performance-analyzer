import unittest
from unittest.mock import patch
from pathlib import Path
from io import StringIO
import pandas as pd
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup
from campaign_data import load_csv, filter_data, aggregate, totals, time_series

ROOT = Path(__file__).resolve().parents[1]

class DataTests(unittest.TestCase):
    def setUp(self):
        self.content = (ROOT / "sample_campaign_performance.csv").read_bytes()
        self.data, _ = load_csv(self.content)

    def test_sample_totals_and_weighted_roi(self):
        result = totals(self.data)
        self.assertEqual(result["spend"], 15100)
        self.assertEqual(result["conversions"], 1203)
        self.assertAlmostEqual(result["roi_percent"], (36090 - 15100) / 15100 * 100)
        custom = self.data.iloc[:2].copy()
        custom["spend"] = [100, 900]
        custom["revenue"] = [300, 900]
        self.assertEqual(totals(custom)["roi_percent"], 20)

    def test_combined_filters_and_empty_selection(self):
        data = self.data.copy()
        data["audience"] = ["Returning" if p == "Facebook" else "New" for p in data["platform"]]
        data["campaign_goal"] = ["Sales" if name == "Back to School" else "Awareness" for name in data["campaign_name"]]
        chosen = filter_data(data, "2026-08-01", "2026-08-31", ["Facebook"], ["Returning"], ["Sales"])
        self.assertEqual(chosen["campaign_id"].tolist(), ["FB002"])
        self.assertTrue(filter_data(data, "2026-07-01", "2026-09-30", [], ["Returning"], ["Sales"]).empty)
        self.assertTrue(filter_data(data, "2027-01-01", "2027-02-01", ["Facebook"], ["Returning"], ["Sales"]).empty)

    def test_time_buckets_preserve_totals(self):
        for interval in ["Daily", "Weekly", "Monthly"]:
            series = time_series(self.data, interval)
            self.assertEqual(series["spend"].sum(), self.data["spend"].sum())
            self.assertEqual(series["conversions"].sum(), self.data["conversions"].sum())
        self.assertEqual(len(time_series(self.data, "Monthly")), 12)

    def test_zero_denominators(self):
        frame = self.data.iloc[:1].copy()
        frame[["spend", "clicks", "conversions", "revenue"]] = 0
        result = totals(frame)
        for field in ["roi_percent", "cpa", "cpc", "conversion_rate_percent"]:
            self.assertTrue(pd.isna(result[field]))

    def test_validation_and_optional_dimensions(self):
        self.assertEqual(self.data["audience"].unique().tolist(), ["Unspecified"])
        raw = pd.read_csv(StringIO(self.content.decode("utf-8-sig")))
        cases = []
        bad = raw.copy(); bad.loc[0, "spend"] = -1; cases.append(bad)
        bad = raw.copy(); bad.loc[0, "end_date"] = "bad"; cases.append(bad)
        bad = raw.copy(); bad.loc[0, "currency"] = "EUR"; cases.append(bad)
        bad = raw.copy(); bad["clicks"] = bad["clicks"].astype(float); bad.loc[0, "clicks"] = 0.5; cases.append(bad)
        bad = raw.copy(); bad.loc[0, "revenue"] = float("inf"); cases.append(bad)
        cases.append(raw.drop(columns="spend"))
        for case in cases:
            with self.subTest(columns=case.columns.tolist()):
                with self.assertRaises(ValueError):
                    load_csv(case.to_csv(index=False).encode("utf-8"))

    def test_daily_csv_with_dimensions_and_x(self):
        payload = b"campaign_id,campaign_name,platform,date,spend,clicks,conversions,revenue,audience,campaign_goal\nA,Test,X,2026-08-01,10,20,2,30,Returning,Sales\n"
        data, _ = load_csv(payload)
        self.assertEqual(data.iloc[0]["platform"], "Twitter")
        self.assertEqual(data.iloc[0]["roi_percent"], 200)
        self.assertEqual(data.iloc[0]["audience"], "Returning")

class ViewTests(unittest.TestCase):
    def setUp(self):
        # Streamlit 1.50's AppTest assumes button groups always return lists.
        # Normalize a single selection to the indices sent by the browser.
        def indices(widget):
            value = widget.value
            choices = [value] if isinstance(value, str) else value or []
            return [widget.options.index(widget.format_func(choice)) for choice in choices]

        adapter = patch.object(ButtonGroup, "indices", property(indices))
        adapter.start()
        self.addCleanup(adapter.stop)
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertEqual(len(self.app.exception), 0)

    def test_all_views_share_filtered_metrics(self):
        self.app.multiselect(key="channels").set_value(["Facebook"]).run()
        expected = ["USD 4,300.00", "8,600", "374", "USD 11,220.00", "160.9%"]
        for view in ["Overview", "Platform Comparison", "Campaign Details", "Time Series"]:
            with self.subTest(view=view):
                self.app.button_group(key="view").set_value([view]).run()
                self.assertEqual(len(self.app.exception), 0)
                self.assertEqual([m.value for m in self.app.metric], expected)
                if view in ["Platform Comparison", "Campaign Details"]:
                    self.assertEqual(set(self.app.dataframe[0].value["Channel"]), {"Facebook"})

        self.app.button_group(key="view").set_value([]).run()
        self.assertEqual(self.app.session_state["view"], "Time Series")
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual([m.value for m in self.app.metric], expected)

    def test_empty_filters_in_every_view_and_reset(self):
        self.app.multiselect(key="channels").set_value([]).run()
        for view in ["Overview", "Platform Comparison", "Campaign Details", "Time Series"]:
            self.app.button_group(key="view").set_value([view]).run()
            self.assertEqual(len(self.app.exception), 0)
            self.assertEqual(len(self.app.metric), 0)
            self.assertTrue(any("No campaigns match these filters" in item.value for item in self.app.info))
        self.app.button[0].click().run()
        self.assertEqual(len(self.app.metric), 5)

    def test_campaign_search(self):
        self.app.button_group(key="view").set_value(["Campaign Details"]).run()
        self.app.text_input(key="search").set_value("FB001").run()
        self.assertEqual(len(self.app.dataframe[0].value), 1)
        self.app.text_input(key="search").set_value("nonexistent campaign").run()
        self.assertTrue(any("No campaigns match your search" in item.value for item in self.app.info))
        self.assertEqual(len(self.app.exception), 0)

    def test_date_and_dimension_filters(self):
        from datetime import date
        self.app.date_input(key="dates").set_value((date(2026, 8, 1), date(2026, 8, 31))).run()
        self.assertEqual(self.app.metric[0].value, "USD 5,200.00")
        for key in ["audiences", "goals"]:
            self.app.multiselect(key=key).set_value([]).run()
            self.assertEqual(len(self.app.metric), 0)
            self.app.multiselect(key=key).set_value(["Unspecified"]).run()
            self.assertEqual(self.app.metric[0].value, "USD 5,200.00")

if __name__ == "__main__":
    unittest.main()



