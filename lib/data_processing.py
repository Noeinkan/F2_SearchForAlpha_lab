# Data processing module
"""
Data fetching, preprocessing, and metric calculations for trading strategies.
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional

# Configure module logger
logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    """Custom exception for data fetching errors."""
    pass


def fetch_data(
    symbol: str,
    start_date: str,
    end_date: str,
    validate: bool = True
) -> pd.DataFrame:
    """
    Fetch historical price data from Yahoo Finance.
    
    Args:
        symbol: Ticker symbol to fetch.
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.
        validate: Whether to validate the returned data.
        
    Returns:
        DataFrame with OHLCV data.
        
    Raises:
        DataFetchError: If data cannot be fetched or is invalid.
    """
    if not symbol or not isinstance(symbol, str):
        raise DataFetchError(f"Invalid symbol: {symbol}")
    
    logger.info(f"Fetching data for {symbol} from {start_date} to {end_date}")
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            raise DataFetchError(
                f"No data available for {symbol} between {start_date} and {end_date}"
            )
        
        df.index = pd.to_datetime(df.index).date
        
        if validate:
            _validate_price_data(df, symbol)
        
        logger.info(f"Successfully fetched {len(df)} rows for {symbol}")
        return df
        
    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {str(e)}")
        raise DataFetchError(f"Failed to fetch data for {symbol}: {str(e)}") from e


def _validate_price_data(df: pd.DataFrame, symbol: str) -> None:
    """
    Validate price data quality.
    
    Args:
        df: DataFrame with price data.
        symbol: Symbol name for error messages.
        
    Raises:
        DataFetchError: If data fails validation.
    """
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise DataFetchError(f"Missing required columns for {symbol}: {missing}")
    
    # Check for excessive NaN values
    nan_pct = df['Close'].isna().sum() / len(df) * 100
    if nan_pct > 10:
        logger.warning(f"{symbol} has {nan_pct:.1f}% NaN values in Close column")


def _get_default_tickers() -> pd.DataFrame:
    """Return a comprehensive list of tickers including US, European stocks and ETFs."""
    tickers = [
        # ============ US STOCKS ============
        # Major Tech
        ('AAPL', 'Apple Inc.', 'S&P 500'),
        ('MSFT', 'Microsoft Corporation', 'S&P 500'),
        ('GOOGL', 'Alphabet Inc. Class A', 'S&P 500'),
        ('GOOG', 'Alphabet Inc. Class C', 'S&P 500'),
        ('AMZN', 'Amazon.com Inc.', 'S&P 500'),
        ('NVDA', 'NVIDIA Corporation', 'S&P 500'),
        ('META', 'Meta Platforms Inc.', 'S&P 500'),
        ('TSLA', 'Tesla Inc.', 'S&P 500'),
        ('AMD', 'Advanced Micro Devices Inc.', 'S&P 500'),
        ('INTC', 'Intel Corporation', 'S&P 500'),
        ('CRM', 'Salesforce Inc.', 'S&P 500'),
        ('ORCL', 'Oracle Corporation', 'S&P 500'),
        ('ADBE', 'Adobe Inc.', 'S&P 500'),
        ('NFLX', 'Netflix Inc.', 'S&P 500'),
        ('CSCO', 'Cisco Systems Inc.', 'S&P 500'),
        ('AVGO', 'Broadcom Inc.', 'S&P 500'),
        ('QCOM', 'Qualcomm Inc.', 'S&P 500'),
        ('TXN', 'Texas Instruments Inc.', 'S&P 500'),
        ('IBM', 'IBM Corporation', 'S&P 500'),
        ('NOW', 'ServiceNow Inc.', 'S&P 500'),
        ('AMAT', 'Applied Materials Inc.', 'S&P 500'),
        ('MU', 'Micron Technology Inc.', 'S&P 500'),
        ('LRCX', 'Lam Research Corp.', 'S&P 500'),
        ('KLAC', 'KLA Corporation', 'S&P 500'),
        ('SNPS', 'Synopsys Inc.', 'S&P 500'),
        ('CDNS', 'Cadence Design Systems', 'S&P 500'),
        ('PANW', 'Palo Alto Networks Inc.', 'S&P 500'),
        ('CRWD', 'CrowdStrike Holdings Inc.', 'NASDAQ'),
        ('ZS', 'Zscaler Inc.', 'NASDAQ'),
        ('PLTR', 'Palantir Technologies Inc.', 'NYSE'),
        ('SNOW', 'Snowflake Inc.', 'NYSE'),
        ('DDOG', 'Datadog Inc.', 'NASDAQ'),
        ('NET', 'Cloudflare Inc.', 'NYSE'),
        ('U', 'Unity Software Inc.', 'NYSE'),
        ('RBLX', 'Roblox Corporation', 'NYSE'),

        # Finance
        ('JPM', 'JPMorgan Chase & Co.', 'S&P 500'),
        ('BAC', 'Bank of America Corp.', 'S&P 500'),
        ('WFC', 'Wells Fargo & Company', 'S&P 500'),
        ('GS', 'Goldman Sachs Group Inc.', 'S&P 500'),
        ('MS', 'Morgan Stanley', 'S&P 500'),
        ('V', 'Visa Inc.', 'S&P 500'),
        ('MA', 'Mastercard Inc.', 'S&P 500'),
        ('AXP', 'American Express Company', 'S&P 500'),
        ('C', 'Citigroup Inc.', 'S&P 500'),
        ('BLK', 'BlackRock Inc.', 'S&P 500'),
        ('SCHW', 'Charles Schwab Corp.', 'S&P 500'),
        ('USB', 'U.S. Bancorp', 'S&P 500'),
        ('PNC', 'PNC Financial Services', 'S&P 500'),
        ('COIN', 'Coinbase Global Inc.', 'NASDAQ'),
        ('SQ', 'Block Inc.', 'NYSE'),
        ('PYPL', 'PayPal Holdings Inc.', 'NASDAQ'),
        ('SOFI', 'SoFi Technologies Inc.', 'NASDAQ'),
        ('HOOD', 'Robinhood Markets Inc.', 'NASDAQ'),

        # Healthcare
        ('JNJ', 'Johnson & Johnson', 'S&P 500'),
        ('UNH', 'UnitedHealth Group Inc.', 'S&P 500'),
        ('PFE', 'Pfizer Inc.', 'S&P 500'),
        ('MRK', 'Merck & Co. Inc.', 'S&P 500'),
        ('ABBV', 'AbbVie Inc.', 'S&P 500'),
        ('LLY', 'Eli Lilly and Company', 'S&P 500'),
        ('TMO', 'Thermo Fisher Scientific', 'S&P 500'),
        ('ABT', 'Abbott Laboratories', 'S&P 500'),
        ('DHR', 'Danaher Corporation', 'S&P 500'),
        ('BMY', 'Bristol-Myers Squibb', 'S&P 500'),
        ('AMGN', 'Amgen Inc.', 'S&P 500'),
        ('GILD', 'Gilead Sciences Inc.', 'S&P 500'),
        ('ISRG', 'Intuitive Surgical Inc.', 'S&P 500'),
        ('VRTX', 'Vertex Pharmaceuticals', 'S&P 500'),
        ('REGN', 'Regeneron Pharmaceuticals', 'S&P 500'),
        ('MRNA', 'Moderna Inc.', 'NASDAQ'),
        ('BNTX', 'BioNTech SE', 'NASDAQ'),

        # Consumer
        ('WMT', 'Walmart Inc.', 'S&P 500'),
        ('PG', 'Procter & Gamble Co.', 'S&P 500'),
        ('KO', 'Coca-Cola Company', 'S&P 500'),
        ('PEP', 'PepsiCo Inc.', 'S&P 500'),
        ('COST', 'Costco Wholesale Corp.', 'S&P 500'),
        ('MCD', 'McDonalds Corp.', 'S&P 500'),
        ('HD', 'Home Depot Inc.', 'S&P 500'),
        ('NKE', 'Nike Inc.', 'S&P 500'),
        ('SBUX', 'Starbucks Corporation', 'S&P 500'),
        ('TGT', 'Target Corporation', 'S&P 500'),
        ('LOW', 'Lowes Companies Inc.', 'S&P 500'),
        ('TJX', 'TJX Companies Inc.', 'S&P 500'),
        ('LULU', 'Lululemon Athletica', 'NASDAQ'),
        ('CMG', 'Chipotle Mexican Grill', 'NYSE'),
        ('YUM', 'Yum! Brands Inc.', 'S&P 500'),
        ('DG', 'Dollar General Corp.', 'NYSE'),
        ('DLTR', 'Dollar Tree Inc.', 'NASDAQ'),

        # Industrial
        ('CAT', 'Caterpillar Inc.', 'S&P 500'),
        ('BA', 'Boeing Company', 'S&P 500'),
        ('GE', 'General Electric Company', 'S&P 500'),
        ('MMM', '3M Company', 'S&P 500'),
        ('HON', 'Honeywell International Inc.', 'S&P 500'),
        ('UPS', 'United Parcel Service Inc.', 'S&P 500'),
        ('RTX', 'RTX Corporation', 'S&P 500'),
        ('LMT', 'Lockheed Martin Corp.', 'S&P 500'),
        ('DE', 'Deere & Company', 'S&P 500'),
        ('FDX', 'FedEx Corporation', 'S&P 500'),
        ('NOC', 'Northrop Grumman Corp.', 'S&P 500'),
        ('GD', 'General Dynamics Corp.', 'S&P 500'),
        ('EMR', 'Emerson Electric Co.', 'S&P 500'),
        ('ETN', 'Eaton Corporation', 'S&P 500'),

        # Energy
        ('XOM', 'Exxon Mobil Corporation', 'S&P 500'),
        ('CVX', 'Chevron Corporation', 'S&P 500'),
        ('COP', 'ConocoPhillips', 'S&P 500'),
        ('SLB', 'Schlumberger NV', 'S&P 500'),
        ('EOG', 'EOG Resources Inc.', 'S&P 500'),
        ('PXD', 'Pioneer Natural Resources', 'S&P 500'),
        ('MPC', 'Marathon Petroleum Corp.', 'S&P 500'),
        ('VLO', 'Valero Energy Corp.', 'S&P 500'),
        ('PSX', 'Phillips 66', 'S&P 500'),
        ('OXY', 'Occidental Petroleum', 'S&P 500'),
        ('HAL', 'Halliburton Company', 'S&P 500'),

        # Telecom & Media
        ('T', 'AT&T Inc.', 'S&P 500'),
        ('VZ', 'Verizon Communications Inc.', 'S&P 500'),
        ('TMUS', 'T-Mobile US Inc.', 'S&P 500'),
        ('DIS', 'Walt Disney Company', 'S&P 500'),
        ('CMCSA', 'Comcast Corporation', 'S&P 500'),
        ('WBD', 'Warner Bros. Discovery', 'NASDAQ'),
        ('PARA', 'Paramount Global', 'NASDAQ'),
        ('NWSA', 'News Corp Class A', 'NASDAQ'),

        # Utilities
        ('NEE', 'NextEra Energy Inc.', 'S&P 500'),
        ('DUK', 'Duke Energy Corp.', 'S&P 500'),
        ('SO', 'Southern Company', 'S&P 500'),
        ('D', 'Dominion Energy Inc.', 'S&P 500'),
        ('AEP', 'American Electric Power', 'S&P 500'),

        # Real Estate
        ('AMT', 'American Tower Corp.', 'S&P 500'),
        ('PLD', 'Prologis Inc.', 'S&P 500'),
        ('CCI', 'Crown Castle Inc.', 'S&P 500'),
        ('EQIX', 'Equinix Inc.', 'S&P 500'),
        ('SPG', 'Simon Property Group', 'S&P 500'),
        ('O', 'Realty Income Corp.', 'S&P 500'),

        # Materials & Mining
        ('TMC', 'The Metals Company Inc.', 'NASDAQ'),  # User requested
        ('LIN', 'Linde plc', 'S&P 500'),
        ('APD', 'Air Products and Chemicals', 'S&P 500'),
        ('SHW', 'Sherwin-Williams Company', 'S&P 500'),
        ('FCX', 'Freeport-McMoRan Inc.', 'S&P 500'),
        ('NEM', 'Newmont Corporation', 'S&P 500'),
        ('NUE', 'Nucor Corporation', 'S&P 500'),
        ('STLD', 'Steel Dynamics Inc.', 'NASDAQ'),
        ('CLF', 'Cleveland-Cliffs Inc.', 'NYSE'),
        ('X', 'United States Steel Corp.', 'NYSE'),
        ('AA', 'Alcoa Corporation', 'NYSE'),
        ('GOLD', 'Barrick Gold Corporation', 'NYSE'),
        ('AEM', 'Agnico Eagle Mines', 'NYSE'),
        ('RIO', 'Rio Tinto plc ADR', 'NYSE'),
        ('BHP', 'BHP Group Ltd ADR', 'NYSE'),
        ('VALE', 'Vale S.A. ADR', 'NYSE'),
        ('SCCO', 'Southern Copper Corp.', 'NYSE'),
        ('MP', 'MP Materials Corp.', 'NYSE'),
        ('LAC', 'Lithium Americas Corp.', 'NYSE'),
        ('ALB', 'Albemarle Corporation', 'NYSE'),
        ('SQM', 'Sociedad Quimica y Minera ADR', 'NYSE'),
        ('LTHM', 'Livent Corporation', 'NYSE'),

        # Electric Vehicles & Clean Energy
        ('RIVN', 'Rivian Automotive Inc.', 'NASDAQ'),
        ('LCID', 'Lucid Group Inc.', 'NASDAQ'),
        ('NIO', 'NIO Inc. ADR', 'NYSE'),
        ('XPEV', 'XPeng Inc. ADR', 'NYSE'),
        ('LI', 'Li Auto Inc. ADR', 'NASDAQ'),
        ('FSR', 'Fisker Inc.', 'NYSE'),
        ('PLUG', 'Plug Power Inc.', 'NASDAQ'),
        ('FCEL', 'FuelCell Energy Inc.', 'NASDAQ'),
        ('BE', 'Bloom Energy Corp.', 'NYSE'),
        ('ENPH', 'Enphase Energy Inc.', 'NASDAQ'),
        ('SEDG', 'SolarEdge Technologies', 'NASDAQ'),
        ('FSLR', 'First Solar Inc.', 'NASDAQ'),
        ('RUN', 'Sunrun Inc.', 'NASDAQ'),
        ('CSIQ', 'Canadian Solar Inc.', 'NASDAQ'),
        ('JKS', 'JinkoSolar Holding ADR', 'NYSE'),

        # Semiconductors (additional)
        ('TSM', 'Taiwan Semiconductor ADR', 'NYSE'),
        ('ASML', 'ASML Holding NV ADR', 'NASDAQ'),
        ('ARM', 'Arm Holdings plc ADR', 'NASDAQ'),
        ('MRVL', 'Marvell Technology Inc.', 'NASDAQ'),
        ('ON', 'ON Semiconductor Corp.', 'NASDAQ'),
        ('SWKS', 'Skyworks Solutions Inc.', 'NASDAQ'),
        ('MPWR', 'Monolithic Power Systems', 'NASDAQ'),
        ('WOLF', 'Wolfspeed Inc.', 'NYSE'),
        ('SLAB', 'Silicon Laboratories', 'NASDAQ'),

        # Aerospace & Defense
        ('AXON', 'Axon Enterprise Inc.', 'NASDAQ'),
        ('LHX', 'L3Harris Technologies', 'NYSE'),
        ('TDG', 'TransDigm Group Inc.', 'NYSE'),
        ('HWM', 'Howmet Aerospace Inc.', 'NYSE'),
        ('LDOS', 'Leidos Holdings Inc.', 'NYSE'),

        # Retail & E-commerce
        ('BABA', 'Alibaba Group ADR', 'NYSE'),
        ('JD', 'JD.com Inc. ADR', 'NASDAQ'),
        ('PDD', 'PDD Holdings Inc. ADR', 'NASDAQ'),
        ('MELI', 'MercadoLibre Inc.', 'NASDAQ'),
        ('SE', 'Sea Limited ADR', 'NYSE'),
        ('SHOP', 'Shopify Inc.', 'NYSE'),
        ('ETSY', 'Etsy Inc.', 'NASDAQ'),
        ('W', 'Wayfair Inc.', 'NYSE'),
        ('CHWY', 'Chewy Inc.', 'NYSE'),

        # Gaming & Entertainment
        ('ATVI', 'Activision Blizzard', 'NASDAQ'),
        ('EA', 'Electronic Arts Inc.', 'NASDAQ'),
        ('TTWO', 'Take-Two Interactive', 'NASDAQ'),
        ('SONY', 'Sony Group Corp. ADR', 'NYSE'),
        ('NTDOY', 'Nintendo Co. ADR', 'OTC'),

        # Biotech & Pharma (additional)
        ('BIIB', 'Biogen Inc.', 'NASDAQ'),
        ('ILMN', 'Illumina Inc.', 'NASDAQ'),
        ('ZTS', 'Zoetis Inc.', 'NYSE'),
        ('IQV', 'IQVIA Holdings Inc.', 'NYSE'),
        ('ALGN', 'Align Technology Inc.', 'NASDAQ'),
        ('DXCM', 'DexCom Inc.', 'NASDAQ'),

        # Travel & Hospitality
        ('MAR', 'Marriott International', 'NASDAQ'),
        ('HLT', 'Hilton Worldwide Holdings', 'NYSE'),
        ('ABNB', 'Airbnb Inc.', 'NASDAQ'),
        ('BKNG', 'Booking Holdings Inc.', 'NASDAQ'),
        ('EXPE', 'Expedia Group Inc.', 'NASDAQ'),
        ('UAL', 'United Airlines Holdings', 'NASDAQ'),
        ('DAL', 'Delta Air Lines Inc.', 'NYSE'),
        ('AAL', 'American Airlines Group', 'NASDAQ'),
        ('LUV', 'Southwest Airlines Co.', 'NYSE'),
        ('CCL', 'Carnival Corporation', 'NYSE'),
        ('RCL', 'Royal Caribbean Cruises', 'NYSE'),
        ('NCLH', 'Norwegian Cruise Line', 'NYSE'),

        # Food & Beverage
        ('MDLZ', 'Mondelez International', 'NASDAQ'),
        ('KHC', 'Kraft Heinz Company', 'NASDAQ'),
        ('GIS', 'General Mills Inc.', 'NYSE'),
        ('K', 'Kellogg Company', 'NYSE'),
        ('HSY', 'Hershey Company', 'NYSE'),
        ('CPB', 'Campbell Soup Company', 'NYSE'),
        ('SJM', 'J.M. Smucker Company', 'NYSE'),
        ('TSN', 'Tyson Foods Inc.', 'NYSE'),
        ('BUD', 'Anheuser-Busch InBev ADR', 'NYSE'),
        ('DEO', 'Diageo plc ADR', 'NYSE'),
        ('STZ', 'Constellation Brands', 'NYSE'),

        # Automotive
        ('F', 'Ford Motor Company', 'NYSE'),
        ('GM', 'General Motors Company', 'NYSE'),
        ('STLA', 'Stellantis NV', 'NYSE'),
        ('TM', 'Toyota Motor Corp. ADR', 'NYSE'),
        ('HMC', 'Honda Motor Co. ADR', 'NYSE'),
        ('RACE', 'Ferrari NV', 'NYSE'),

        # SPACs & Recent IPOs
        ('DWAC', 'Digital World Acquisition', 'NASDAQ'),
        ('IONQ', 'IonQ Inc.', 'NYSE'),
        ('RGTI', 'Rigetti Computing Inc.', 'NASDAQ'),

        # ============ EUROPEAN STOCKS ============
        # UK Stocks (.L = London Stock Exchange)
        ('SHEL.L', 'Shell plc', 'LSE'),
        ('BP.L', 'BP plc', 'LSE'),
        ('HSBA.L', 'HSBC Holdings plc', 'LSE'),
        ('AZN.L', 'AstraZeneca plc', 'LSE'),
        ('GSK.L', 'GSK plc', 'LSE'),
        ('ULVR.L', 'Unilever plc', 'LSE'),
        ('RIO.L', 'Rio Tinto plc', 'LSE'),
        ('DGE.L', 'Diageo plc', 'LSE'),
        ('LLOY.L', 'Lloyds Banking Group', 'LSE'),
        ('BARC.L', 'Barclays plc', 'LSE'),
        ('VOD.L', 'Vodafone Group plc', 'LSE'),
        ('BT-A.L', 'BT Group plc', 'LSE'),
        ('GLEN.L', 'Glencore plc', 'LSE'),
        ('AAL.L', 'Anglo American plc', 'LSE'),
        ('BA.L', 'BAE Systems plc', 'LSE'),
        ('RR.L', 'Rolls-Royce Holdings', 'LSE'),
        ('TSCO.L', 'Tesco plc', 'LSE'),

        # German Stocks (.DE = XETRA)
        ('SAP.DE', 'SAP SE', 'XETRA'),
        ('SIE.DE', 'Siemens AG', 'XETRA'),
        ('ALV.DE', 'Allianz SE', 'XETRA'),
        ('BAS.DE', 'BASF SE', 'XETRA'),
        ('BMW.DE', 'BMW AG', 'XETRA'),
        ('VOW3.DE', 'Volkswagen AG', 'XETRA'),
        ('MBG.DE', 'Mercedes-Benz Group AG', 'XETRA'),
        ('DTE.DE', 'Deutsche Telekom AG', 'XETRA'),
        ('DBK.DE', 'Deutsche Bank AG', 'XETRA'),
        ('ADS.DE', 'adidas AG', 'XETRA'),
        ('MUV2.DE', 'Munich Re', 'XETRA'),
        ('IFX.DE', 'Infineon Technologies', 'XETRA'),
        ('BEI.DE', 'Beiersdorf AG', 'XETRA'),
        ('HEN3.DE', 'Henkel AG', 'XETRA'),

        # French Stocks (.PA = Euronext Paris)
        ('OR.PA', 'LOreal SA', 'Euronext Paris'),
        ('MC.PA', 'LVMH', 'Euronext Paris'),
        ('TTE.PA', 'TotalEnergies SE', 'Euronext Paris'),
        ('SAN.PA', 'Sanofi SA', 'Euronext Paris'),
        ('AIR.PA', 'Airbus SE', 'Euronext Paris'),
        ('BNP.PA', 'BNP Paribas SA', 'Euronext Paris'),
        ('SU.PA', 'Schneider Electric SE', 'Euronext Paris'),
        ('AI.PA', 'Air Liquide SA', 'Euronext Paris'),
        ('KER.PA', 'Kering SA', 'Euronext Paris'),
        ('RMS.PA', 'Hermes International', 'Euronext Paris'),
        ('CAP.PA', 'Capgemini SE', 'Euronext Paris'),
        ('DSY.PA', 'Dassault Systemes SE', 'Euronext Paris'),
        ('ORA.PA', 'Orange SA', 'Euronext Paris'),
        ('DG.PA', 'Vinci SA', 'Euronext Paris'),

        # Dutch Stocks (.AS = Euronext Amsterdam)
        ('ASML.AS', 'ASML Holding NV', 'Euronext Amsterdam'),
        ('PHIA.AS', 'Koninklijke Philips NV', 'Euronext Amsterdam'),
        ('INGA.AS', 'ING Groep NV', 'Euronext Amsterdam'),
        ('ABN.AS', 'ABN AMRO Bank NV', 'Euronext Amsterdam'),
        ('AD.AS', 'Koninklijke Ahold Delhaize', 'Euronext Amsterdam'),
        ('UNA.AS', 'Unilever NV', 'Euronext Amsterdam'),
        ('HEIA.AS', 'Heineken NV', 'Euronext Amsterdam'),

        # Swiss Stocks (.SW = SIX Swiss Exchange)
        ('NESN.SW', 'Nestle SA', 'SIX'),
        ('ROG.SW', 'Roche Holding AG', 'SIX'),
        ('NOVN.SW', 'Novartis AG', 'SIX'),
        ('UBS.SW', 'UBS Group AG', 'SIX'),
        ('CSGN.SW', 'Credit Suisse Group', 'SIX'),
        ('ZURN.SW', 'Zurich Insurance Group', 'SIX'),
        ('ABBN.SW', 'ABB Ltd', 'SIX'),
        ('LONN.SW', 'Lonza Group AG', 'SIX'),
        ('SIKA.SW', 'Sika AG', 'SIX'),
        ('GIVN.SW', 'Givaudan SA', 'SIX'),

        # Italian Stocks (.MI = Borsa Italiana)
        ('ENI.MI', 'Eni SpA', 'Borsa Italiana'),
        ('ENEL.MI', 'Enel SpA', 'Borsa Italiana'),
        ('ISP.MI', 'Intesa Sanpaolo', 'Borsa Italiana'),
        ('UCG.MI', 'UniCredit SpA', 'Borsa Italiana'),
        ('G.MI', 'Assicurazioni Generali', 'Borsa Italiana'),
        ('RACE.MI', 'Ferrari NV', 'Borsa Italiana'),
        ('STM.MI', 'STMicroelectronics', 'Borsa Italiana'),

        # Spanish Stocks (.MC = Madrid Stock Exchange)
        ('SAN.MC', 'Banco Santander SA', 'BME'),
        ('BBVA.MC', 'BBVA SA', 'BME'),
        ('TEF.MC', 'Telefonica SA', 'BME'),
        ('IBE.MC', 'Iberdrola SA', 'BME'),
        ('ITX.MC', 'Inditex SA', 'BME'),
        ('REP.MC', 'Repsol SA', 'BME'),

        # Nordic Stocks
        ('NOVO-B.CO', 'Novo Nordisk A/S', 'Copenhagen'),
        ('CARL-B.CO', 'Carlsberg A/S', 'Copenhagen'),
        ('MAERSK-B.CO', 'A.P. Moller-Maersk', 'Copenhagen'),
        ('VOLV-B.ST', 'Volvo AB', 'Stockholm'),
        ('ERIC-B.ST', 'Ericsson', 'Stockholm'),
        ('ATCO-A.ST', 'Atlas Copco AB', 'Stockholm'),
        ('HM-B.ST', 'H&M', 'Stockholm'),
        ('SPOT.ST', 'Spotify Technology', 'Stockholm'),
        ('NHY.OL', 'Norsk Hydro ASA', 'Oslo'),
        ('EQNR.OL', 'Equinor ASA', 'Oslo'),
        ('DNB.OL', 'DNB ASA', 'Oslo'),

        # ============ US INDEX ETFs ============
        ('SPY', 'SPDR S&P 500 ETF', 'Index ETF'),
        ('QQQ', 'Invesco QQQ Trust', 'Index ETF'),
        ('DIA', 'SPDR Dow Jones Industrial Average ETF', 'Index ETF'),
        ('IWM', 'iShares Russell 2000 ETF', 'Index ETF'),
        ('IWF', 'iShares Russell 1000 Growth ETF', 'Index ETF'),
        ('IWD', 'iShares Russell 1000 Value ETF', 'Index ETF'),
        ('VTI', 'Vanguard Total Stock Market ETF', 'Index ETF'),
        ('VOO', 'Vanguard S&P 500 ETF', 'Index ETF'),
        ('VTV', 'Vanguard Value ETF', 'Index ETF'),
        ('VUG', 'Vanguard Growth ETF', 'Index ETF'),
        ('VIG', 'Vanguard Dividend Appreciation ETF', 'Index ETF'),
        ('VYM', 'Vanguard High Dividend Yield ETF', 'Index ETF'),
        ('SCHD', 'Schwab US Dividend Equity ETF', 'Index ETF'),
        ('MDY', 'SPDR S&P MidCap 400 ETF', 'Index ETF'),
        ('IJH', 'iShares Core S&P Mid-Cap ETF', 'Index ETF'),
        ('IJR', 'iShares Core S&P Small-Cap ETF', 'Index ETF'),

        # ============ SECTOR ETFs ============
        ('XLK', 'Technology Select Sector SPDR', 'Sector ETF'),
        ('XLF', 'Financial Select Sector SPDR', 'Sector ETF'),
        ('XLE', 'Energy Select Sector SPDR', 'Sector ETF'),
        ('XLV', 'Health Care Select Sector SPDR', 'Sector ETF'),
        ('XLY', 'Consumer Discretionary SPDR', 'Sector ETF'),
        ('XLP', 'Consumer Staples Select SPDR', 'Sector ETF'),
        ('XLI', 'Industrial Select Sector SPDR', 'Sector ETF'),
        ('XLB', 'Materials Select Sector SPDR', 'Sector ETF'),
        ('XLU', 'Utilities Select Sector SPDR', 'Sector ETF'),
        ('XLRE', 'Real Estate Select Sector SPDR', 'Sector ETF'),
        ('XLC', 'Communication Services SPDR', 'Sector ETF'),
        ('VGT', 'Vanguard Information Technology ETF', 'Sector ETF'),
        ('VHT', 'Vanguard Health Care ETF', 'Sector ETF'),
        ('VFH', 'Vanguard Financials ETF', 'Sector ETF'),
        ('VDE', 'Vanguard Energy ETF', 'Sector ETF'),
        ('VCR', 'Vanguard Consumer Discretionary', 'Sector ETF'),
        ('VDC', 'Vanguard Consumer Staples ETF', 'Sector ETF'),

        # ============ THEMATIC & SPECIALTY ETFs ============
        ('ARKK', 'ARK Innovation ETF', 'Thematic ETF'),
        ('ARKG', 'ARK Genomic Revolution ETF', 'Thematic ETF'),
        ('ARKF', 'ARK Fintech Innovation ETF', 'Thematic ETF'),
        ('ARKQ', 'ARK Autonomous Tech & Robotics', 'Thematic ETF'),
        ('ARKW', 'ARK Next Generation Internet', 'Thematic ETF'),
        ('SOXX', 'iShares Semiconductor ETF', 'Thematic ETF'),
        ('SMH', 'VanEck Semiconductor ETF', 'Thematic ETF'),
        ('XBI', 'SPDR S&P Biotech ETF', 'Thematic ETF'),
        ('IBB', 'iShares Biotechnology ETF', 'Thematic ETF'),
        ('HACK', 'ETFMG Prime Cyber Security', 'Thematic ETF'),
        ('CIBR', 'First Trust Cybersecurity ETF', 'Thematic ETF'),
        ('ROBO', 'ROBO Global Robotics & Auto ETF', 'Thematic ETF'),
        ('BOTZ', 'Global X Robotics & AI ETF', 'Thematic ETF'),
        ('DRIV', 'Global X Autonomous & EV ETF', 'Thematic ETF'),
        ('LIT', 'Global X Lithium & Battery ETF', 'Thematic ETF'),
        ('TAN', 'Invesco Solar ETF', 'Thematic ETF'),
        ('ICLN', 'iShares Global Clean Energy ETF', 'Thematic ETF'),
        ('QCLN', 'First Trust NASDAQ Clean Edge', 'Thematic ETF'),
        ('PBW', 'Invesco WilderHill Clean Energy', 'Thematic ETF'),
        ('ACES', 'ALPS Clean Energy ETF', 'Thematic ETF'),
        ('MSOS', 'AdvisorShares Pure US Cannabis', 'Thematic ETF'),
        ('MJ', 'ETFMG Alternative Harvest ETF', 'Thematic ETF'),
        ('JETS', 'US Global Jets ETF', 'Thematic ETF'),
        ('BETZ', 'Roundhill Sports Betting ETF', 'Thematic ETF'),
        ('NERD', 'Roundhill Video Games ETF', 'Thematic ETF'),
        ('GAMR', 'Wedbush ETFMG Video Game Tech', 'Thematic ETF'),
        ('HERO', 'Global X Video Games & Esports', 'Thematic ETF'),
        ('SPYG', 'SPDR Portfolio S&P 500 Growth', 'Thematic ETF'),
        ('SPYV', 'SPDR Portfolio S&P 500 Value', 'Thematic ETF'),
        ('MTUM', 'iShares MSCI USA Momentum Factor', 'Thematic ETF'),
        ('QUAL', 'iShares MSCI USA Quality Factor', 'Thematic ETF'),
        ('USMV', 'iShares MSCI USA Min Vol Factor', 'Thematic ETF'),

        # ============ INTERNATIONAL ETFs ============
        ('EFA', 'iShares MSCI EAFE ETF', 'International ETF'),
        ('VEA', 'Vanguard FTSE Developed Markets', 'International ETF'),
        ('VWO', 'Vanguard FTSE Emerging Markets', 'International ETF'),
        ('EEM', 'iShares MSCI Emerging Markets', 'International ETF'),
        ('IEMG', 'iShares Core MSCI EM ETF', 'International ETF'),
        ('VGK', 'Vanguard FTSE Europe ETF', 'International ETF'),
        ('EWG', 'iShares MSCI Germany ETF', 'International ETF'),
        ('EWU', 'iShares MSCI United Kingdom', 'International ETF'),
        ('EWJ', 'iShares MSCI Japan ETF', 'International ETF'),
        ('MCHI', 'iShares MSCI China ETF', 'International ETF'),
        ('FXI', 'iShares China Large-Cap ETF', 'International ETF'),
        ('KWEB', 'KraneShares CSI China Internet', 'International ETF'),
        ('EWY', 'iShares MSCI South Korea ETF', 'International ETF'),
        ('EWT', 'iShares MSCI Taiwan ETF', 'International ETF'),
        ('INDA', 'iShares MSCI India ETF', 'International ETF'),
        ('EWZ', 'iShares MSCI Brazil ETF', 'International ETF'),
        ('EWC', 'iShares MSCI Canada ETF', 'International ETF'),
        ('EWA', 'iShares MSCI Australia ETF', 'International ETF'),
        ('VXUS', 'Vanguard Total International', 'International ETF'),

        # ============ BOND ETFs ============
        ('BND', 'Vanguard Total Bond Market ETF', 'Bond ETF'),
        ('AGG', 'iShares Core US Aggregate Bond', 'Bond ETF'),
        ('TLT', 'iShares 20+ Year Treasury Bond', 'Bond ETF'),
        ('IEF', 'iShares 7-10 Year Treasury Bond', 'Bond ETF'),
        ('SHY', 'iShares 1-3 Year Treasury Bond', 'Bond ETF'),
        ('TIP', 'iShares TIPS Bond ETF', 'Bond ETF'),
        ('LQD', 'iShares iBoxx Investment Grade', 'Bond ETF'),
        ('HYG', 'iShares iBoxx High Yield Corp', 'Bond ETF'),
        ('JNK', 'SPDR Bloomberg High Yield Bond', 'Bond ETF'),
        ('VCIT', 'Vanguard Intermediate-Term Corp', 'Bond ETF'),
        ('VCSH', 'Vanguard Short-Term Corp Bond', 'Bond ETF'),
        ('BNDX', 'Vanguard Total Intl Bond ETF', 'Bond ETF'),
        ('EMB', 'iShares JP Morgan USD EM Bond', 'Bond ETF'),
        ('MUB', 'iShares National Muni Bond ETF', 'Bond ETF'),

        # ============ COMMODITY ETFs ============
        ('GLD', 'SPDR Gold Shares', 'Commodity ETF'),
        ('IAU', 'iShares Gold Trust', 'Commodity ETF'),
        ('SLV', 'iShares Silver Trust', 'Commodity ETF'),
        ('GDX', 'VanEck Gold Miners ETF', 'Commodity ETF'),
        ('GDXJ', 'VanEck Junior Gold Miners ETF', 'Commodity ETF'),
        ('USO', 'United States Oil Fund', 'Commodity ETF'),
        ('UNG', 'United States Natural Gas Fund', 'Commodity ETF'),
        ('DBC', 'Invesco DB Commodity Index', 'Commodity ETF'),
        ('DBA', 'Invesco DB Agriculture Fund', 'Commodity ETF'),
        ('PDBC', 'Invesco Optimum Yield Commodity', 'Commodity ETF'),
        ('COPX', 'Global X Copper Miners ETF', 'Commodity ETF'),
        ('PALL', 'abrdn Palladium ETF', 'Commodity ETF'),
        ('PPLT', 'abrdn Platinum ETF', 'Commodity ETF'),
        ('URA', 'Global X Uranium ETF', 'Commodity ETF'),

        # ============ LEVERAGED & INVERSE ETFs ============
        ('TQQQ', 'ProShares UltraPro QQQ', 'Leveraged ETF'),
        ('SQQQ', 'ProShares UltraPro Short QQQ', 'Leveraged ETF'),
        ('UPRO', 'ProShares UltraPro S&P 500', 'Leveraged ETF'),
        ('SPXU', 'ProShares UltraPro Short S&P', 'Leveraged ETF'),
        ('SSO', 'ProShares Ultra S&P 500', 'Leveraged ETF'),
        ('SDS', 'ProShares UltraShort S&P 500', 'Leveraged ETF'),
        ('QLD', 'ProShares Ultra QQQ', 'Leveraged ETF'),
        ('QID', 'ProShares UltraShort QQQ', 'Leveraged ETF'),
        ('SOXL', 'Direxion Semiconductor Bull 3X', 'Leveraged ETF'),
        ('SOXS', 'Direxion Semiconductor Bear 3X', 'Leveraged ETF'),
        ('LABU', 'Direxion Biotech Bull 3X', 'Leveraged ETF'),
        ('LABD', 'Direxion Biotech Bear 3X', 'Leveraged ETF'),
        ('TNA', 'Direxion Small Cap Bull 3X', 'Leveraged ETF'),
        ('TZA', 'Direxion Small Cap Bear 3X', 'Leveraged ETF'),
        ('FNGU', 'MicroSectors FANG+ Index 3X', 'Leveraged ETF'),
        ('FNGD', 'MicroSectors FANG+ Index -3X', 'Leveraged ETF'),
        ('TECL', 'Direxion Technology Bull 3X', 'Leveraged ETF'),
        ('TECS', 'Direxion Technology Bear 3X', 'Leveraged ETF'),

        # ============ CRYPTOCURRENCY ETFs ============
        ('BITO', 'ProShares Bitcoin Strategy ETF', 'Crypto ETF'),
        ('BTF', 'Valkyrie Bitcoin Strategy ETF', 'Crypto ETF'),
        ('GBTC', 'Grayscale Bitcoin Trust', 'Crypto ETF'),
        ('ETHE', 'Grayscale Ethereum Trust', 'Crypto ETF'),
        ('BITQ', 'Bitwise Crypto Industry ETF', 'Crypto ETF'),
        ('BLOK', 'Amplify Transformational Data', 'Crypto ETF'),
    ]
    return pd.DataFrame(tickers, columns=['Symbol', 'Security', 'Index'])


def _fetch_sp500_from_github() -> Optional[pd.DataFrame]:
    """Fetch S&P 500 constituents from GitHub datasets repo."""
    import requests
    url = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(response.text))
        df = df.rename(columns={'Name': 'Security'})
        df['Index'] = 'S&P 500'
        return df[['Symbol', 'Security', 'Index']]
    except Exception as e:
        logger.warning(f"Failed to fetch from GitHub: {e}")
        return None


def _fetch_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch tickers from Wikipedia with proper headers."""
    import requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        # Fetch S&P 500 tickers
        sp500_resp = requests.get(
            'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
            headers=headers, timeout=10
        )
        sp500_resp.raise_for_status()
        sp500 = pd.read_html(sp500_resp.text)[0]
        sp500['Index'] = 'S&P 500'

        # Fetch NASDAQ-100 tickers
        nasdaq_resp = requests.get(
            'https://en.wikipedia.org/wiki/Nasdaq-100',
            headers=headers, timeout=10
        )
        nasdaq_resp.raise_for_status()
        nasdaq100 = pd.read_html(nasdaq_resp.text)[4]
        nasdaq100['Index'] = 'NASDAQ-100'
        nasdaq100 = nasdaq100.rename(columns={'Ticker': 'Symbol'})

        all_tickers = pd.concat([
            sp500[['Symbol', 'Security', 'Index']],
            nasdaq100[['Symbol', 'Company', 'Index']].rename(columns={'Company': 'Security'})
        ], ignore_index=True)

        return all_tickers
    except Exception as e:
        logger.warning(f"Failed to fetch from Wikipedia: {e}")
        return None


def get_all_tickers() -> pd.DataFrame:
    """
    Get list of S&P 500, NASDAQ-100 tickers and popular ETFs.

    Uses multiple sources with fallback:
    1. GitHub datasets repo (most reliable)
    2. Wikipedia (comprehensive but may block)
    3. Built-in default list (always works)

    Returns:
        DataFrame with Symbol, Security name, and Index columns.
    """
    logger.info("Fetching ticker list")

    # Try GitHub first (most reliable)
    tickers_df = _fetch_sp500_from_github()

    # Try Wikipedia as backup
    if tickers_df is None:
        logger.info("Trying Wikipedia as fallback")
        tickers_df = _fetch_from_wikipedia()

    # Use default list as final fallback
    if tickers_df is None:
        logger.info("Using default ticker list")
        tickers_df = _get_default_tickers()
    else:
        # Add additional stocks and ETFs to fetched data
        additional_tickers = _get_default_tickers()
        tickers_df = pd.concat([tickers_df, additional_tickers], ignore_index=True)

    tickers_df = tickers_df.drop_duplicates(subset='Symbol')
    logger.info(f"Loaded {len(tickers_df)} tickers")
    return tickers_df


def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """
    Calculate maximum drawdown from cumulative returns.
    
    Args:
        df: DataFrame with 'Cumulative_Returns' column.
        
    Returns:
        Maximum drawdown as a decimal (negative value).
    """
    if 'Cumulative_Returns' not in df.columns:
        logger.warning("Cumulative_Returns column not found, returning 0")
        return 0.0
    cumulative_returns = df['Cumulative_Returns']
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    return drawdown.min()


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe ratio.
    
    Args:
        returns: Series of periodic returns.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Number of trading periods per year.
        
    Returns:
        Annualized Sharpe ratio.
    """
    if returns.std() == 0:
        return 0.0
    excess_returns = returns - risk_free_rate / periods_per_year
    return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()


def calculate_win_rate(df: pd.DataFrame) -> float:
    """
    Calculate the win rate of trading strategy.
    
    Args:
        df: DataFrame with 'Strategy_Returns' column.
        
    Returns:
        Win rate as a decimal.
    """
    if 'Strategy_Returns' not in df.columns:
        return 0.0
    profitable_trades = (df['Strategy_Returns'] > 0).sum()
    total_trades = len(df['Strategy_Returns'])
    return profitable_trades / total_trades if total_trades > 0 else 0.0


def calculate_profit_factor(df: pd.DataFrame) -> float:
    """
    Calculate the profit factor (gross profits / gross losses).
    
    Args:
        df: DataFrame with 'Strategy_Returns' column.
        
    Returns:
        Profit factor (inf if no losses).
    """
    if 'Strategy_Returns' not in df.columns:
        return 0.0
    gross_profits = df['Strategy_Returns'][df['Strategy_Returns'] > 0].sum()
    gross_losses = abs(df['Strategy_Returns'][df['Strategy_Returns'] < 0].sum())
    return gross_profits / gross_losses if gross_losses != 0 else np.inf

def calculate_max_consecutive(series: pd.Series) -> int:
    """
    Calculate maximum consecutive occurrences in a boolean series.
    
    Args:
        series: Boolean series.
        
    Returns:
        Maximum consecutive count.
    """
    if series.empty:
        return 0
    groups = (series != series.shift()).cumsum()
    return max((series.groupby(groups).cumcount() + 1).max(), 0)


def calculate_average_trade_duration(df: pd.DataFrame) -> float:
    """
    Calculate average trade duration in days.
    
    Args:
        df: DataFrame with 'Units' column.
        
    Returns:
        Average trade duration in days.
    """
    if 'Units' not in df.columns:
        return 0.0
        
    try:
        trade_starts = df.index[df['Units'] != df['Units'].shift(1)]
        trade_ends = df.index[df['Units'] != df['Units'].shift(-1)]
        
        if len(trade_starts) > 0 and len(trade_ends) > 0:
            trade_durations = [
                (end - start).days 
                for start, end in zip(trade_starts, trade_ends) 
                if end > start
            ]
            return sum(trade_durations) / len(trade_durations) if trade_durations else 0.0
    except Exception as e:
        logger.warning(f"Error calculating trade duration: {e}")
    return 0.0

# Data processing module

def create_backtest_results(
    df: pd.DataFrame,
    ticker: str,
    initial_capital: float,
    buy_strategy: List[str],
    sell_strategy: List[str]
) -> Dict:
    """
    Create a dictionary of backtest results and metrics.
    
    Args:
        df: DataFrame with backtest results.
        ticker: Ticker symbol.
        initial_capital: Initial capital used.
        buy_strategy: List of buy indicator names.
        sell_strategy: List of sell indicator names.
        
    Returns:
        Dictionary with backtest metrics.
    """
    try:
        return {
            'ticker': ticker,
            'start_date': df.index[0].strftime('%Y-%m-%d') if hasattr(df.index[0], 'strftime') else str(df.index[0]),
            'end_date': df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1]),
            'initial_capital': initial_capital,
            'final_portfolio_value': df['Portfolio_Value'].iloc[-1],
            'total_return': (df['Cumulative_Returns'].iloc[-1] - 1) * 100,
            'market_return': ((df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1) * 100,
            'buy_strategy': buy_strategy,
            'sell_strategy': sell_strategy,
            'max_drawdown': calculate_max_drawdown(df),
            'sharpe_ratio': calculate_sharpe_ratio(df['Strategy_Returns']),
            'win_rate': calculate_win_rate(df),
            'profit_factor': calculate_profit_factor(df),
            'avg_trade_duration': calculate_average_trade_duration(df)
        }
    except Exception as e:
        logger.error(f"Error creating backtest results: {e}")
        raise