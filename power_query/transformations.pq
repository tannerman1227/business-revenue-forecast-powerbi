// Vantage Process Group — Power Query M
//
// pDataRoot is a text parameter. Point it at the clone's data folder
// and keep the trailing backslash, for example
//   C:\Projects\business-revenue-forecast-powerbi\data\
// Every CSV query concatenates that parameter with the file name.
// Refresh after changing it. The Scenario and _Measures tables are
// entered in M and do not read a file.
//
pDataRoot = "C:\\Data\\business-revenue-forecast-powerbi\\data\\" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// dim_date
shared dim_date =
let
    Source = Csv.Document(File.Contents(pDataRoot & "dim_date.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"DateKey", Int64.Type}, {"Date", type date}, {"Year", Int64.Type}, {"FiscalYear", Int64.Type}, {"FiscalYearLabel", type text}, {"Quarter", Int64.Type}, {"QuarterName", type text}, {"YearQuarter", type text}, {"MonthNumber", Int64.Type}, {"MonthName", type text}, {"MonthShort", type text}, {"MonthYear", type text}, {"YearMonth", type text}, {"YearMonthSort", Int64.Type}, {"Day", Int64.Type}, {"MonthStart", type date}, {"IsMonthStart", type text}, {"CalendarStage", type text}}),
    LogicalMonthStart = Table.TransformColumns(Typed, {{"IsMonthStart", each _ = "True", type logical}}),
    WithQuarterSort = Table.AddColumn(LogicalMonthStart, "YearQuarterSort", each [Year] * 10 + [Quarter], Int64.Type)
in
    WithQuarterSort


// dim_region
shared dim_region =
let
    Source = Csv.Document(File.Contents(pDataRoot & "dim_region.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"RegionKey", Int64.Type}, {"Region", type text}, {"RegionCode", type text}, {"ManagementGroup", type text}, {"Currency", type text}})
in
    Typed


// dim_product_line
shared dim_product_line =
let
    Source = Csv.Document(File.Contents(pDataRoot & "dim_product_line.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"ProductLineKey", Int64.Type}, {"ProductLine", type text}, {"ProductCode", type text}, {"RevenueType", type text}, {"UnitOfMeasure", type text}, {"PortfolioRole", type text}})
in
    Typed


// dim_customer_segment
shared dim_customer_segment =
let
    Source = Csv.Document(File.Contents(pDataRoot & "dim_customer_segment.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"SegmentKey", Int64.Type}, {"Segment", type text}, {"SegmentCode", type text}, {"BuyingMotion", type text}})
in
    Typed


// fact_revenue_actuals
shared fact_revenue_actuals =
let
    Source = Csv.Document(File.Contents(pDataRoot & "fact_revenue_actuals.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"DateKey", Int64.Type}, {"Date", type date}, {"RegionKey", Int64.Type}, {"ProductLineKey", Int64.Type}, {"SegmentKey", Int64.Type}, {"Revenue", Currency.Type}, {"COGS", Currency.Type}, {"GrossProfit", Currency.Type}, {"OpEx", Currency.Type}, {"EBITDA", Currency.Type}, {"VolumeUnits", Int64.Type}})
in
    Typed


// fact_budget_forecast
shared fact_budget_forecast =
let
    Source = Csv.Document(File.Contents(pDataRoot & "fact_budget_forecast.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"DateKey", Int64.Type}, {"Date", type date}, {"RegionKey", Int64.Type}, {"ProductLineKey", Int64.Type}, {"SegmentKey", Int64.Type}, {"Scenario", type text}, {"Revenue", Currency.Type}, {"COGS", Currency.Type}, {"GrossProfit", Currency.Type}, {"OpEx", Currency.Type}, {"EBITDA", Currency.Type}})
in
    Typed


// Scenario
shared Scenario =
let
    Source = Table.FromRows(
        {
            {"Budget", "Plan", 1},
            {"Backtest", "Model Validation", 2},
            {"Forecast - Downside", "Rolling Forecast", 3},
            {"Forecast - Base", "Rolling Forecast", 4},
            {"Forecast - Upside", "Rolling Forecast", 5}
        },
        {"Scenario", "ScenarioGroup", "SortOrder"}
    ),
    Typed = Table.TransformColumnTypes(Source, {{"Scenario", type text}, {"ScenarioGroup", type text}, {"SortOrder", Int64.Type}})
in
    Typed


// _Measures
shared _Measures =
let
    Source = Table.FromRows(Json.Document("[[]]"), {"Column1"}),
    Empty = Table.SelectRows(Source, each false),
    Removed = Table.RemoveColumns(Empty, {"Column1"})
in
    Removed
