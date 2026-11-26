// Census Bureau retail and food services sales.
// UseLiveCensus = true downloads the two public workbooks on refresh.
// UseLiveCensus = false reads data/fact_retail_sales.csv from DataRoot.
// Forecast files always come from DataRoot. Run scripts/forecast_model.py to rebuild them.
// Set DataRoot to the full path of the data folder, for example:
//   C:\Users\YourName\business-revenue-forecast-powerbi\data

// ===== Query: UseLiveCensus | expression | Logical =====
false meta [IsParameterQuery = true, Type = "Logical", IsParameterQueryRequired = true]

// ===== Query: DataRoot | expression | Text =====
"SET_DATA_FOLDER" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]

// ===== Query: fnAsNumber | expression | Function =====
(value as any) as nullable number =>
    if value is number then Number.From(value)
    else try Number.FromText(Text.Trim(Text.From(value))) otherwise null

// ===== Query: fnCodeKey | expression | Function =====
(value as any) as nullable text =>
    let
        Codes = {
            "441", "442", "443", "444", "445", "446", "447",
            "448", "451", "452", "453", "454", "722"
        },
        TextValue =
            if value is number then Text.From(Number.RoundDown(value, 0))
            else Text.Trim(try Text.From(value) otherwise ""),
        Digits = Text.Select(TextValue, {"0".."9"})
    in
        if List.Contains(Codes, Digits) and Text.Length(Digits) = Text.Length(TextValue) then Digits else null

// ===== Query: fnSectorKey | expression | Function =====
(code as text) as text =>
    Record.Field(
        [
            #"441" = "MOTOR",
            #"442" = "FURNITURE",
            #"443" = "ELECTRONICS",
            #"444" = "BUILDING",
            #"445" = "FOOD_STORES",
            #"446" = "HEALTH",
            #"447" = "GASOLINE",
            #"448" = "CLOTHING",
            #"451" = "SPORTING",
            #"452" = "GENERAL",
            #"453" = "MISC",
            #"454" = "NONSTORE",
            #"722" = "FOOD_SERVICE"
        ],
        code
    )

// ===== Query: fnParseMonth | expression | Function =====
(label as any, fallbackYear as nullable number) as nullable date =>
    let
        Raw = Text.Trim(try Text.From(label) otherwise ""),
        Clean = Text.Replace(Text.Replace(Text.Replace(Raw, "(p)", ""), "(r)", ""), "(a)", ""),
        Parts = List.Select(Text.Split(Text.Replace(Clean, ".", " "), " "), each _ <> ""),
        Token = if List.Count(Parts) >= 1 then Text.Lower(Text.Start(Parts{0}, 3)) else "",
        MonthNames = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"},
        Found = List.PositionOf(MonthNames, Token),
        YearText = if List.Count(Parts) >= 2 then Text.Select(Parts{1}, {"0".."9"}) else "",
        YearNum = if Text.Length(YearText) = 4 then Number.FromText(YearText) else fallbackYear
    in
        if Found < 0 or YearNum = null then null else #date(YearNum, Found + 1, 1)

// ===== Query: fnSheetRows | expression | Function =====
(data as table) as list =>
    let
        Cols = Table.ColumnNames(data),
        Recs = Table.ToRecords(data)
    in
        List.Transform(Recs, (row) => List.Transform(Cols, (col) => Record.Field(row, col)))

// ===== Query: fnHistorySheet | expression | Function =====
(data as table) as table =>
    let
        Rows = fnSheetRows(data),
        Upper = (row as list, idx as number) as text =>
            try Text.Upper(Text.Trim(Text.From(row{idx}))) otherwise "",
        NotAt = List.PositionOf(List.Transform(Rows, each Text.Contains(Upper(_, 1), "NOT ADJUSTED")), true, Occurrence.First),
        AdjAt = List.PositionOf(
            List.Transform(Rows, each Text.Contains(Upper(_, 1), "ADJUSTED") and not Text.Contains(Upper(_, 1), "NOT")),
            true,
            Occurrence.First
        ),
        Empty = #table(type table [SectorKey = text, Date = date, Kind = text, Value = number], {}),
        Result =
            if NotAt < 1 or AdjAt < 0 then
                Empty
            else
                let
                    Header = Rows{NotAt - 1},
                    Months = List.Select(
                        List.Transform({0 .. List.Count(Header) - 1}, (i) => {i, fnParseMonth(Header{i}, null)}),
                        each _{1} <> null
                    ),
                    Take = (slice as list, kind as text) as list =>
                        List.Combine(
                            List.Transform(
                                slice,
                                (row) =>
                                    let
                                        Code = fnCodeKey(row{0})
                                    in
                                        if Code = null then
                                            {}
                                        else
                                            List.Transform(
                                                List.Select(Months, (m) => fnAsNumber(row{m{0}}) <> null),
                                                (m) => [
                                                    SectorKey = fnSectorKey(Code),
                                                    Date = m{1},
                                                    Kind = kind,
                                                    Value = fnAsNumber(row{m{0}})
                                                ]
                                            )
                            )
                        ),
                    NsaRows = Take(List.Range(Rows, NotAt + 1, AdjAt - NotAt - 1), "NSA"),
                    SaRows = Take(List.Range(Rows, AdjAt + 1, List.Count(Rows) - AdjAt - 1), "SA")
                in
                    Table.FromRecords(NsaRows & SaRows, type table [SectorKey = text, Date = date, Kind = text, Value = number])
    in
        Result

// ===== Query: fnAdvanceSheet | expression | Function =====
(data as table) as table =>
    let
        Rows = fnSheetRows(data),
        HasOct = List.Transform(
            Rows,
            (row) => List.AnyTrue(List.Transform(row, (cell) => Text.Contains(try Text.Upper(Text.From(cell)) otherwise "", "OCT")))
        ),
        MonthRow = List.PositionOf(HasOct, true, Occurrence.First),
        Empty = #table(type table [SectorKey = text, Date = date, Kind = text, Value = number], {}),
        Result =
            if MonthRow < 2 then
                Empty
            else
                let
                    SectionRow = Rows{MonthRow - 2},
                    YearRow = Rows{MonthRow - 1},
                    Labels = Rows{MonthRow},
                    Wide = List.Max({List.Count(SectionRow), List.Count(YearRow), List.Count(Labels)}),
                    State = List.Accumulate(
                        {0 .. Wide - 1},
                        [Year = null, Section = null, Columns = {}],
                        (state, index) =>
                            let
                                SecText = try Text.Upper(Text.From(SectionRow{index})) otherwise "",
                                Section =
                                    if Text.Contains(SecText, "NOT ADJUSTED") then "NSA"
                                    else if Text.Contains(SecText, "ADJUST") then "SA"
                                    else state[Section],
                                YearCell = if index < List.Count(YearRow) then YearRow{index} else null,
                                YearDigits = Text.Select(try Text.From(YearCell) otherwise "", {"0".."9"}),
                                Year =
                                    if YearCell is number and YearCell > 1900 then Number.RoundDown(YearCell, 0)
                                    else if Text.Length(YearDigits) = 4 then Number.FromText(YearDigits)
                                    else state[Year],
                                Stamp = fnParseMonth(if index < List.Count(Labels) then Labels{index} else null, Year),
                                Columns =
                                    if Section <> null and Stamp <> null then state[Columns] & {{index, Section, Stamp}}
                                    else state[Columns]
                            in
                                [Year = Year, Section = Section, Columns = Columns]
                    ),
                    Columns = State[Columns],
                    Walked = List.Accumulate(
                        List.Skip(Rows, MonthRow + 1),
                        [Pending = null, Out = {}],
                        (state, row) =>
                            let
                                Code = fnCodeKey(if List.Count(row) > 0 then row{0} else null),
                                HasValue = List.AnyTrue(List.Transform(Columns, (col) => fnAsNumber(if col{0} < List.Count(row) then row{col{0}} else null) <> null)),
                                Use = if Code <> null and HasValue then Code else if HasValue then state[Pending] else null,
                                Added =
                                    if Use = null then
                                        {}
                                    else
                                        List.Transform(
                                            List.Select(Columns, (col) => fnAsNumber(if col{0} < List.Count(row) then row{col{0}} else null) <> null),
                                            (col) => [
                                                SectorKey = fnSectorKey(Use),
                                                Date = col{2},
                                                Kind = col{1},
                                                Value = fnAsNumber(row{col{0}})
                                            ]
                                        )
                            in
                                [
                                    Pending = if Code <> null and not HasValue then Code else null,
                                    Out = state[Out] & Added
                                ]
                    )
                in
                    Table.FromRecords(Walked[Out], type table [SectorKey = text, Date = date, Kind = text, Value = number])
    in
        Result

// ===== Query: fnLiveSales | expression | Function =====
() as table =>
    let
        HistoryBook = Excel.Workbook(Web.Contents("https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx"), false, true),
        AdvanceBook = Excel.Workbook(Web.Contents("https://www.census.gov/retail/marts/www/marts_current.xlsx"), false, true),
        NameCol = if List.Contains(Table.ColumnNames(HistoryBook), "Name") then "Name" else "Item",
        YearSheets = Table.SelectRows(
            HistoryBook,
            each [Kind] = "Sheet" and try Number.FromText(Text.From(Record.Field(_, NameCol))) > 1900 otherwise false
        ),
        History = Table.Combine(List.Transform(YearSheets[Data], each fnHistorySheet(_))),
        AdvanceSheet = Table.SelectRows(AdvanceBook, each [Kind] = "Sheet"){0}[Data],
        Advance = fnAdvanceSheet(AdvanceSheet),
        Tagged = Table.Combine({
            Table.AddColumn(History, "Priority", each 0, Int64.Type),
            Table.AddColumn(Advance, "Priority", each 1, Int64.Type)
        }),
        Grouped = Table.Group(
            Tagged,
            {"Date", "SectorKey"},
            {
                {
                    "SalesNSA",
                    each
                        let
                            t = Table.Sort(Table.SelectRows(_, each [Kind] = "NSA"), {{"Priority", Order.Descending}})
                        in
                            if Table.IsEmpty(t) then null else t{0}[Value],
                    type number
                },
                {
                    "SalesSA",
                    each
                        let
                            t = Table.Sort(Table.SelectRows(_, each [Kind] = "SA"), {{"Priority", Order.Descending}})
                        in
                            if Table.IsEmpty(t) then null else t{0}[Value],
                    type number
                }
            }
        ),
        Clean = Table.SelectRows(Grouped, each [SalesNSA] <> null and [SalesSA] <> null),
        Typed = Table.TransformColumnTypes(
            Table.SelectColumns(Clean, {"Date", "SectorKey", "SalesNSA", "SalesSA"}),
            {{"Date", type date}, {"SectorKey", type text}, {"SalesNSA", type number}, {"SalesSA", type number}}
        )
    in
        Table.Sort(Typed, {{"Date", Order.Ascending}, {"SectorKey", Order.Ascending}})

// ===== Query: fnLocalCsv | expression | Function =====
(fileName as text, columnTypes as list) as table =>
    let
        Root = Text.TrimEnd(Text.Replace(DataRoot, "\", "/"), "/"),
        Raw = Csv.Document(
            File.Contents(Root & "/" & fileName),
            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
        ),
        Promoted = Table.PromoteHeaders(Raw, [PromoteAllScalars = true])
    in
        Table.TransformColumnTypes(Promoted, columnTypes)

// ===== Query: FactRetailSales | table | Table =====
let
    Local = fnLocalCsv(
        "fact_retail_sales.csv",
        {{"Date", type date}, {"SectorKey", type text}, {"SalesNSA", type number}, {"SalesSA", type number}}
    ),
    Result = if UseLiveCensus then fnLiveSales() else Local
in
    Result

// ===== Query: DimSector | table | Table =====
let
    Source = #table(
        type table [
            SectorKey = text,
            SectorName = text,
            SectorShort = text,
            SectorGroup = text,
            Channel = text,
            KindOfBusiness = text,
            FredSeriesNSA = text,
            FredSeriesSA = text,
            FredUrlNSA = text,
            FredUrlSA = text,
            SortOrder = Int64.Type
        ],
        {
            {"MOTOR", "Motor Vehicle and Parts Dealers", "Motor Vehicles", "Durable Goods", "Store Retail", "441", "RSMVPDN", "RSMVPD", "https://fred.stlouisfed.org/series/RSMVPDN", "https://fred.stlouisfed.org/series/RSMVPD", 10},
            {"FURNITURE", "Furniture and Home Furnishings Stores", "Furniture & Home", "Durable Goods", "Store Retail", "442", "RSFHFSN", "RSFHFS", "https://fred.stlouisfed.org/series/RSFHFSN", "https://fred.stlouisfed.org/series/RSFHFS", 20},
            {"ELECTRONICS", "Electronics and Appliance Stores", "Electronics", "Durable Goods", "Store Retail", "443", "RSEASN", "RSEAS", "https://fred.stlouisfed.org/series/RSEASN", "https://fred.stlouisfed.org/series/RSEAS", 30},
            {"BUILDING", "Building Materials and Garden Equipment", "Building Materials", "Durable Goods", "Store Retail", "444", "RSBMGESDN", "RSBMGESD", "https://fred.stlouisfed.org/series/RSBMGESDN", "https://fred.stlouisfed.org/series/RSBMGESD", 40},
            {"FOOD_STORES", "Food and Beverage Stores", "Food & Beverage Stores", "Staples", "Store Retail", "445", "RSDBSN", "RSDBS", "https://fred.stlouisfed.org/series/RSDBSN", "https://fred.stlouisfed.org/series/RSDBS", 50},
            {"HEALTH", "Health and Personal Care Stores", "Health & Personal Care", "Staples", "Store Retail", "446", "RSHPCSN", "RSHPCS", "https://fred.stlouisfed.org/series/RSHPCSN", "https://fred.stlouisfed.org/series/RSHPCS", 60},
            {"GASOLINE", "Gasoline Stations", "Gasoline Stations", "Staples", "Store Retail", "447", "RSGASSN", "RSGASS", "https://fred.stlouisfed.org/series/RSGASSN", "https://fred.stlouisfed.org/series/RSGASS", 70},
            {"CLOTHING", "Clothing and Clothing Accessories Stores", "Clothing", "Discretionary", "Store Retail", "448", "RSCCASN", "RSCCAS", "https://fred.stlouisfed.org/series/RSCCASN", "https://fred.stlouisfed.org/series/RSCCAS", 80},
            {"SPORTING", "Sporting Goods, Hobby, Musical Instrument, and Book Stores", "Sporting Goods & Hobby", "Discretionary", "Store Retail", "451", "RSSGHBMSN", "RSSGHBMS", "https://fred.stlouisfed.org/series/RSSGHBMSN", "https://fred.stlouisfed.org/series/RSSGHBMS", 90},
            {"GENERAL", "General Merchandise Stores", "General Merchandise", "Staples", "Store Retail", "452", "RSGMSN", "RSGMS", "https://fred.stlouisfed.org/series/RSGMSN", "https://fred.stlouisfed.org/series/RSGMS", 100},
            {"MISC", "Miscellaneous Store Retailers", "Miscellaneous Stores", "Discretionary", "Store Retail", "453", "RSMSRN", "RSMSR", "https://fred.stlouisfed.org/series/RSMSRN", "https://fred.stlouisfed.org/series/RSMSR", 110},
            {"NONSTORE", "Nonstore Retailers", "Nonstore Retailers", "Nonstore", "Nonstore Retail", "454", "RSNSRN", "RSNSR", "https://fred.stlouisfed.org/series/RSNSRN", "https://fred.stlouisfed.org/series/RSNSR", 120},
            {"FOOD_SERVICE", "Food Services and Drinking Places", "Food Services", "Food Services", "Food Services", "722", "RSFSDPN", "RSFSDP", "https://fred.stlouisfed.org/series/RSFSDPN", "https://fred.stlouisfed.org/series/RSFSDP", 130}
        }
    )
in
    Source

// ===== Query: DimDate | table | Table =====
let
    Dates = List.Distinct(FactRetailSales[Date]),
    FirstDate = List.Min(Dates),
    LastActual = List.Max(Dates),
    LastDate = Date.AddMonths(LastActual, 12),
    AllDates = List.Generate(() => FirstDate, each _ <= LastDate, each Date.AddMonths(_, 1)),
    Base = Table.TransformColumnTypes(Table.FromList(AllDates, Splitter.SplitByNothing(), {"Date"}), {{"Date", type date}}),
    MonthNames = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"},
    MonthShorts = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"},
    AddYear = Table.AddColumn(Base, "Year", each Date.Year([Date]), Int64.Type),
    AddQuarter = Table.AddColumn(AddYear, "Quarter", each Date.QuarterOfYear([Date]), Int64.Type),
    AddQuarterLabel = Table.AddColumn(AddQuarter, "QuarterLabel", each Text.From([Year]) & " Q" & Text.From([Quarter]), type text),
    AddMonthNumber = Table.AddColumn(AddQuarterLabel, "MonthNumber", each Date.Month([Date]), Int64.Type),
    AddMonthName = Table.AddColumn(AddMonthNumber, "MonthName", each MonthNames{[MonthNumber] - 1}, type text),
    AddMonthShort = Table.AddColumn(AddMonthName, "MonthShort", each MonthShorts{[MonthNumber] - 1}, type text),
    AddYearMonth = Table.AddColumn(AddMonthShort, "YearMonth", each Date.ToText([Date], "yyyy-MM"), type text),
    AddLabel = Table.AddColumn(AddYearMonth, "MonthYearLabel", each [MonthShort] & " " & Text.From([Year]), type text)
in
    AddLabel

// ===== Query: FactForecast | table | Table =====
fnLocalCsv(
    "fact_forecast.csv",
    {
        {"Date", type date},
        {"SectorKey", type text},
        {"Horizon", Int64.Type},
        {"ForecastNSA", type number},
        {"Lower80", type number},
        {"Upper80", type number},
        {"ReconcileFactor", type number},
        {"Model", type text}
    }
)

// ===== Query: ForecastTotal | table | Table =====
fnLocalCsv(
    "forecast_total.csv",
    {
        {"Date", type date},
        {"Horizon", Int64.Type},
        {"ForecastNSA", type number},
        {"Lower80", type number},
        {"Upper80", type number},
        {"Model", type text}
    }
)

// ===== Query: FactBacktest | table | Table =====
fnLocalCsv(
    "fact_backtest.csv",
    {
        {"Date", type date},
        {"SectorKey", type text},
        {"Horizon", Int64.Type},
        {"ActualNSA", Int64.Type},
        {"ForecastNSA", type number},
        {"SeasonalNaiveNSA", Int64.Type},
        {"Lower80", type number},
        {"Upper80", type number},
        {"ReconcileFactor", type number},
        {"Error", type number},
        {"AbsError", type number},
        {"AbsPctError", type number},
        {"Model", type text}
    }
)

// ===== Query: BacktestTotal | table | Table =====
fnLocalCsv(
    "backtest_total.csv",
    {
        {"Date", type date},
        {"Horizon", Int64.Type},
        {"ForecastNSA", type number},
        {"Lower80", type number},
        {"Upper80", type number},
        {"Model", type text},
        {"ActualNSA", Int64.Type},
        {"SeasonalNaiveNSA", Int64.Type},
        {"Error", type number},
        {"AbsError", type number},
        {"AbsPctError", type number}
    }
)
