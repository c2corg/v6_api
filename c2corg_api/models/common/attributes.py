# coding: utf-8
"""
Domain value enumerations used across the application.

Every ``list[str]`` that formerly lived here has been replaced by a
:class:`SafeStrEnum` subclass.  ``SafeStrEnum`` inherits from
:class:`enum.StrEnum` so members **are** strings — ``==``, ``in``,
``json.dumps``, iteration, ``len()`` all work transparently.

A custom metaclass is used so that ``"value" in MyEnum`` works on
Python < 3.12 (where the stdlib raises ``TypeError``).
"""

from enum import EnumMeta, StrEnum

# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------


class _StrEnumContainsMeta(EnumMeta):
    """Metaclass that allows ``"value" in MyEnum`` on Python < 3.12."""

    def __contains__(cls, item):  # noqa: N805
        if isinstance(item, str) and not isinstance(item, cls):
            return item in cls._value2member_map_
        return super().__contains__(item)


class SafeStrEnum(StrEnum, metaclass=_StrEnumContainsMeta):
    """StrEnum whose class supports ``"value" in EnumCls`` on Python 3.11."""

    pass


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


class DefaultLangs(SafeStrEnum):
    fr = 'fr'
    it = 'it'
    de = 'de'
    en = 'en'
    es = 'es'
    ca = 'ca'
    eu = 'eu'
    sl = 'sl'
    zh = 'zh'


langs_priority = ['fr', 'en', 'it', 'de', 'es', 'ca', 'eu', 'sl', 'zh']


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


class Activities(SafeStrEnum):
    skitouring = 'skitouring'
    snow_ice_mixed = 'snow_ice_mixed'
    mountain_climbing = 'mountain_climbing'
    rock_climbing = 'rock_climbing'
    ice_climbing = 'ice_climbing'
    hiking = 'hiking'
    snowshoeing = 'snowshoeing'
    paragliding = 'paragliding'
    mountain_biking = 'mountain_biking'
    via_ferrata = 'via_ferrata'
    slacklining = 'slacklining'


# ---------------------------------------------------------------------------
# Waypoints
# ---------------------------------------------------------------------------


class WaypointTypes(SafeStrEnum):
    summit = 'summit'  # sommet
    pass_ = 'pass'  # col
    lake = 'lake'  # lac
    waterfall = 'waterfall'  # cascade
    locality = 'locality'  # lieu-dit (v5: vallon)
    bisse = 'bisse'  # bisse
    canyon = 'canyon'  # canyon
    access = 'access'  # acces
    climbing_outdoor = 'climbing_outdoor'  # site d'escalade
    climbing_indoor = 'climbing_indoor'  # S.A.E.
    hut = 'hut'  # refuge
    gite = 'gite'  # gite
    shelter = 'shelter'  # abri
    bivouac = 'bivouac'  # bivouac
    camp_site = 'camp_site'  # camping
    base_camp = 'base_camp'  # camp de base
    local_product = 'local_product'  # produit locaux
    paragliding_takeoff = 'paragliding_takeoff'  # deco
    paragliding_landing = 'paragliding_landing'  # attero
    cave = 'cave'  # grotte
    waterpoint = 'waterpoint'  # point d'eau/source
    weather_station = 'weather_station'  # station meteo
    webcam = 'webcam'  # webcam
    virtual = 'virtual'  # sur-WP virtuel
    slackline_spot = 'slackline_spot'  # slackline
    misc = 'misc'  # divers


class ClimbingOutdoorTypes(SafeStrEnum):
    single = 'single'
    multi = 'multi'
    bloc = 'bloc'
    psicobloc = 'psicobloc'


class ClimbingIndoorTypes(SafeStrEnum):
    pitch = 'pitch'
    bloc = 'bloc'


class PublicTransportationTypes(SafeStrEnum):
    train = 'train'
    bus = 'bus'
    service_on_demand = 'service_on_demand'
    boat = 'boat'


class ProductTypes(SafeStrEnum):
    farm_sale = 'farm_sale'  # vente chez le producteur
    restaurant = 'restaurant'
    grocery = 'grocery'
    bar = 'bar'
    sport_shop = 'sport_shop'


class GroundTypes(SafeStrEnum):
    prairie = 'prairie'
    scree = 'scree'  # eboulis
    snow = 'snow'


class WeatherStationTypes(SafeStrEnum):
    temperature = 'temperature'
    wind_speed = 'wind_speed'
    wind_direction = 'wind_direction'
    humidity = 'humidity'
    pressure = 'pressure'
    precipitation = 'precipitation'  # sans rechauffeur
    precipitation_heater = 'precipitation_heater'  # avec rechauffeur
    snow_height = 'snow_height'
    insolation = 'insolation'


class RainProofTypes(SafeStrEnum):
    exposed = 'exposed'
    partly_protected = 'partly_protected'
    protected = 'protected'
    inside = 'inside'


class PublicTransportationRatings(SafeStrEnum):
    good_service = 'good service'  # service regulier
    seasonal_service = 'seasonal service'  # service saisonnier
    poor_service = 'poor service'  # service reduit
    nearby_service = 'nearby service'  # service a proximite
    unknown_service = 'unknown service'  # service inconnu
    no_service = 'no service'  # pas de service


# Cotation deco/attero
class ParaglidingRatings(SafeStrEnum):
    rating_1 = '1'
    rating_2 = '2'
    rating_3 = '3'
    rating_4 = '4'


class ChildrenProofTypes(SafeStrEnum):
    very_safe = 'very_safe'
    safe = 'safe'
    dangerous = 'dangerous'
    very_dangerous = 'very_dangerous'


class SnowClearanceRatings(SafeStrEnum):
    often = 'often'
    sometimes = 'sometimes'
    progressive = 'progressive'
    naturally = 'naturally'
    closed_in_winter = 'closed_in_winter'
    non_applicable = 'non_applicable'


class ExpositionRatings(SafeStrEnum):
    E1 = 'E1'
    E2 = 'E2'
    E3 = 'E3'
    E4 = 'E4'


class RockTypes(SafeStrEnum):
    basalte = 'basalte'
    calcaire = 'calcaire'
    conglomerat = 'conglomerat'
    craie = 'craie'
    gneiss = 'gneiss'
    gres = 'gres'
    granit = 'granit'
    migmatite = 'migmatite'
    mollasse_calcaire = 'mollasse_calcaire'
    pouding = 'pouding'
    quartzite = 'quartzite'
    rhyolite = 'rhyolite'
    schiste = 'schiste'
    trachyte = 'trachyte'
    artificial = 'artificial'


class OrientationTypes(SafeStrEnum):
    N = 'N'
    NE = 'NE'
    E = 'E'
    SE = 'SE'
    S = 'S'
    SW = 'SW'
    W = 'W'
    NW = 'NW'


class Months(SafeStrEnum):
    jan = 'jan'
    feb = 'feb'
    mar = 'mar'
    apr = 'apr'
    may = 'may'
    jun = 'jun'
    jul = 'jul'
    aug = 'aug'
    sep = 'sep'
    oct = 'oct'
    nov = 'nov'
    dec = 'dec'


class ParkingFeeTypes(SafeStrEnum):
    yes = 'yes'
    seasonal = 'seasonal'
    no = 'no'


class ClimbingStyles(SafeStrEnum):
    slab = 'slab'  # dalle
    vertical = 'vertical'  # vertical
    overhang = 'overhang'  # devers/surplomb
    roof = 'roof'  # toit
    small_pillar = 'small_pillar'  # colonnettes
    crack_dihedral = 'crack_dihedral'  # fissure/diedre


class AccessTimes(SafeStrEnum):
    t_1min = '1min'
    t_5min = '5min'
    t_10min = '10min'
    t_15min = '15min'
    t_20min = '20min'
    t_30min = '30min'
    t_45min = '45min'
    t_1h = '1h'
    t_1h30 = '1h30'
    t_2h = '2h'
    t_2h30 = '2h30'
    t_3h = '3h'
    t_3h_plus = '3h+'


class ClimbingRatings(SafeStrEnum):
    grade_2 = '2'
    grade_3a = '3a'
    grade_3b = '3b'
    grade_3c = '3c'
    grade_4a = '4a'
    grade_4b = '4b'
    grade_4c = '4c'
    grade_5a = '5a'
    grade_5a_plus = '5a+'
    grade_5b = '5b'
    grade_5b_plus = '5b+'
    grade_5c = '5c'
    grade_5c_plus = '5c+'
    grade_6a = '6a'
    grade_6a_plus = '6a+'
    grade_6b = '6b'
    grade_6b_plus = '6b+'
    grade_6c = '6c'
    grade_6c_plus = '6c+'
    grade_7a = '7a'
    grade_7a_plus = '7a+'
    grade_7b = '7b'
    grade_7b_plus = '7b+'
    grade_7c = '7c'
    grade_7c_plus = '7c+'
    grade_8a = '8a'
    grade_8a_plus = '8a+'
    grade_8b = '8b'
    grade_8b_plus = '8b+'
    grade_8c = '8c'
    grade_8c_plus = '8c+'
    grade_9a = '9a'
    grade_9a_plus = '9a+'
    grade_9b = '9b'
    grade_9b_plus = '9b+'
    grade_9c = '9c'
    grade_9c_plus = '9c+'


class EquipmentRatings(SafeStrEnum):
    P1 = 'P1'
    P1_plus = 'P1+'
    P2 = 'P2'
    P2_plus = 'P2+'
    P3 = 'P3'
    P3_plus = 'P3+'
    P4 = 'P4'
    P4_plus = 'P4+'


class RouteTypes(SafeStrEnum):
    return_same_way = 'return_same_way'  # aller-retour
    loop = 'loop'  # boucle
    loop_hut = 'loop_hut'  # boucle avec retour au refuge
    traverse = 'traverse'  # traversee
    raid = 'raid'  # raid
    expedition = 'expedition'  # expe


class RouteDurationTypes(SafeStrEnum):
    duration_1 = '1'
    duration_2 = '2'
    duration_3 = '3'
    duration_4 = '4'
    duration_5 = '5'
    duration_6 = '6'
    duration_7 = '7'
    duration_8 = '8'
    duration_9 = '9'
    duration_10 = '10'
    duration_10_plus = '10+'


class GlacierGearTypes(SafeStrEnum):
    no = 'no'
    glacier_safety_gear = 'glacier_safety_gear'
    crampons_spring = 'crampons_spring'
    crampons_req = 'crampons_req'
    glacier_crampons = 'glacier_crampons'


class RouteConfigurationTypes(SafeStrEnum):
    edge = 'edge'
    pillar = 'pillar'
    face = 'face'
    corridor = 'corridor'
    goulotte = 'goulotte'
    glacier = 'glacier'


class SkiRatings(SafeStrEnum):
    ski_1_1 = '1.1'
    ski_1_2 = '1.2'
    ski_1_3 = '1.3'
    ski_2_1 = '2.1'
    ski_2_2 = '2.2'
    ski_2_3 = '2.3'
    ski_3_1 = '3.1'
    ski_3_2 = '3.2'
    ski_3_3 = '3.3'
    ski_4_1 = '4.1'
    ski_4_2 = '4.2'
    ski_4_3 = '4.3'
    ski_5_1 = '5.1'
    ski_5_2 = '5.2'
    ski_5_3 = '5.3'
    ski_5_4 = '5.4'
    ski_5_5 = '5.5'
    ski_5_6 = '5.6'


class LabandeSkiRatings(SafeStrEnum):
    S1 = 'S1'
    S2 = 'S2'
    S3 = 'S3'
    S4 = 'S4'
    S5 = 'S5'
    S6 = 'S6'
    S7 = 'S7'


class GlobalRatings(SafeStrEnum):
    F = 'F'
    F_plus = 'F+'
    PD_minus = 'PD-'
    PD = 'PD'
    PD_plus = 'PD+'
    AD_minus = 'AD-'
    AD = 'AD'
    AD_plus = 'AD+'
    D_minus = 'D-'
    D = 'D'
    D_plus = 'D+'
    TD_minus = 'TD-'
    TD = 'TD'
    TD_plus = 'TD+'
    ED_minus = 'ED-'
    ED = 'ED'
    ED_plus = 'ED+'
    ED4 = 'ED4'
    ED5 = 'ED5'
    ED6 = 'ED6'
    ED7 = 'ED7'


class EngagementRatings(SafeStrEnum):
    I = 'I'  # noqa E741
    II = 'II'
    III = 'III'
    IV = 'IV'
    V = 'V'
    VI = 'VI'


class RiskRatings(SafeStrEnum):
    X1 = 'X1'
    X2 = 'X2'
    X3 = 'X3'
    X4 = 'X4'
    X5 = 'X5'


class IceRatings(SafeStrEnum):
    grade_1 = '1'
    grade_2 = '2'
    grade_3 = '3'
    grade_3_plus = '3+'
    grade_4 = '4'
    grade_4_plus = '4+'
    grade_5 = '5'
    grade_5_plus = '5+'
    grade_6 = '6'
    grade_6_plus = '6+'
    grade_7 = '7'
    grade_7_plus = '7+'


class MixedRatings(SafeStrEnum):
    M1 = 'M1'
    M2 = 'M2'
    M3 = 'M3'
    M3_plus = 'M3+'
    M4 = 'M4'
    M4_plus = 'M4+'
    M5 = 'M5'
    M5_plus = 'M5+'
    M6 = 'M6'
    M6_plus = 'M6+'
    M7 = 'M7'
    M7_plus = 'M7+'
    M8 = 'M8'
    M8_plus = 'M8+'
    M9 = 'M9'
    M9_plus = 'M9+'
    M10 = 'M10'
    M10_plus = 'M10+'
    M11 = 'M11'
    M11_plus = 'M11+'
    M12 = 'M12'
    M12_plus = 'M12+'


class ExpositionRockRatings(SafeStrEnum):
    E1 = 'E1'
    E2 = 'E2'
    E3 = 'E3'
    E4 = 'E4'
    E5 = 'E5'
    E6 = 'E6'


class AidRatings(SafeStrEnum):
    A0 = 'A0'
    A0_plus = 'A0+'
    A1 = 'A1'
    A1_plus = 'A1+'
    A2 = 'A2'
    A2_plus = 'A2+'
    A3 = 'A3'
    A3_plus = 'A3+'
    A4 = 'A4'
    A4_plus = 'A4+'
    A5 = 'A5'
    A5_plus = 'A5+'


class ViaFerrataRatings(SafeStrEnum):
    K1 = 'K1'
    K2 = 'K2'
    K3 = 'K3'
    K4 = 'K4'
    K5 = 'K5'
    K6 = 'K6'


class HikingRatings(SafeStrEnum):
    T1 = 'T1'
    T2 = 'T2'
    T3 = 'T3'
    T4 = 'T4'
    T5 = 'T5'


class SnowshoeRatings(SafeStrEnum):
    R1 = 'R1'
    R2 = 'R2'
    R3 = 'R3'
    R4 = 'R4'
    R5 = 'R5'


class MtbUpRatings(SafeStrEnum):
    M1 = 'M1'
    M2 = 'M2'
    M3 = 'M3'
    M4 = 'M4'
    M5 = 'M5'


class MtbDownRatings(SafeStrEnum):
    V1 = 'V1'
    V2 = 'V2'
    V3 = 'V3'
    V4 = 'V4'
    V5 = 'V5'


class MapEditors(SafeStrEnum):
    IGN = 'IGN'
    Swisstopo = 'Swisstopo'
    Escursionista = 'Escursionista'


class MapScales(SafeStrEnum):
    scale_25000 = '25000'
    scale_50000 = '50000'
    scale_100000 = '100000'


class AreaTypes(SafeStrEnum):
    range = 'range'
    admin_limits = 'admin_limits'
    country = 'country'


class FrequentationTypes(SafeStrEnum):
    quiet = 'quiet'
    some = 'some'
    crowded = 'crowded'
    overcrowded = 'overcrowded'


class AccessConditions(SafeStrEnum):
    cleared = 'cleared'
    snowy = 'snowy'
    closed_snow = 'closed_snow'
    closed_cleared = 'closed_cleared'


class LiftStatus(SafeStrEnum):
    open = 'open'
    closed = 'closed'


class ConditionRatings(SafeStrEnum):
    excellent = 'excellent'
    good = 'good'
    average = 'average'
    poor = 'poor'
    awful = 'awful'


class SnowQualityRatings(SafeStrEnum):
    excellent = 'excellent'
    good = 'good'
    average = 'average'
    poor = 'poor'
    awful = 'awful'


class SnowQuantityRatings(SafeStrEnum):
    excellent = 'excellent'
    good = 'good'
    average = 'average'
    poor = 'poor'
    awful = 'awful'


class GlacierRatings(SafeStrEnum):
    easy = 'easy'
    possible = 'possible'
    difficult = 'difficult'
    impossible = 'impossible'


class AvalancheSigns(SafeStrEnum):
    no = 'no'
    danger_sign = 'danger_sign'
    recent_avalanche = 'recent_avalanche'
    natural_avalanche = 'natural_avalanche'
    accidental_avalanche = 'accidental_avalanche'


class HutStatus(SafeStrEnum):
    open_guarded = 'open_guarded'
    open_non_guarded = 'open_non_guarded'
    closed_hut = 'closed_hut'


class ImageCategories(SafeStrEnum):
    landscapes = 'landscapes'
    detail = 'detail'
    action = 'action'
    track = 'track'
    rise = 'rise'
    descent = 'descent'
    topo = 'topo'
    people = 'people'
    fauna = 'fauna'
    flora = 'flora'
    nivology = 'nivology'
    geology = 'geology'
    hut = 'hut'
    equipment = 'equipment'
    book = 'book'
    help = 'help'
    misc = 'misc'


class ImageTypes(SafeStrEnum):
    collaborative = 'collaborative'
    personal = 'personal'
    copyright = 'copyright'


class UserCategories(SafeStrEnum):
    amateur = 'amateur'
    mountain_guide = 'mountain_guide'
    mountain_leader = 'mountain_leader'
    ski_instructor = 'ski_instructor'
    climbing_instructor = 'climbing_instructor'
    mountainbike_instructor = 'mountainbike_instructor'
    paragliding_instructor = 'paragliding_instructor'
    hut_warden = 'hut_warden'
    ski_patroller = 'ski_patroller'
    avalanche_forecaster = 'avalanche_forecaster'
    club = 'club'
    institution = 'institution'


class QualityTypes(SafeStrEnum):
    empty = 'empty'
    draft = 'draft'
    medium = 'medium'
    fine = 'fine'
    great = 'great'


class CustodianshipTypes(SafeStrEnum):
    accessible_when_wardened = 'accessible_when_wardened'
    always_accessible = 'always_accessible'
    key_needed = 'key_needed'
    no_warden = 'no_warden'


class ArticleCategories(SafeStrEnum):
    mountain_environment = 'mountain_environment'
    gear = 'gear'
    technical = 'technical'
    topoguide_supplements = 'topoguide_supplements'
    soft_mobility = 'soft_mobility'
    expeditions = 'expeditions'
    stories = 'stories'
    c2c_meetings = 'c2c_meetings'
    tags = 'tags'
    site_info = 'site_info'
    association = 'association'


class ArticleTypes(SafeStrEnum):
    collab = 'collab'
    personal = 'personal'


class FeedChangeTypes(SafeStrEnum):
    created = 'created'
    updated = 'updated'
    added_photos = 'added_photos'


class BookTypes(SafeStrEnum):
    topo = 'topo'
    environment = 'environment'
    historical = 'historical'
    biography = 'biography'
    photos_art = 'photos-art'
    novel = 'novel'
    technics = 'technics'
    tourism = 'tourism'
    magazine = 'magazine'


class Mailinglists(SafeStrEnum):
    avalanche = 'avalanche'
    lawinen = 'lawinen'
    valanghe = 'valanghe'
    avalanche_en = 'avalanche.en'
    meteofrance_38 = 'meteofrance-38'
    meteofrance_74 = 'meteofrance-74'
    meteofrance_73 = 'meteofrance-73'
    meteofrance_04 = 'meteofrance-04'
    meteofrance_05 = 'meteofrance-05'
    meteofrance_06 = 'meteofrance-06'
    meteofrance_31 = 'meteofrance-31'
    meteofrance_64 = 'meteofrance-64'
    meteofrance_65 = 'meteofrance-65'
    meteofrance_66 = 'meteofrance-66'
    meteofrance_09 = 'meteofrance-09'
    meteofrance_andorre = 'meteofrance-andorre'
    meteofrance_2a = 'meteofrance-2a'
    meteofrance_2b = 'meteofrance-2b'
    aran = 'aran'
    catalunya = 'catalunya'


class EventActivities(SafeStrEnum):
    sport_climbing = 'sport_climbing'
    multipitch_climbing = 'multipitch_climbing'
    alpine_climbing = 'alpine_climbing'
    snow_ice_mixed = 'snow_ice_mixed'
    ice_climbing = 'ice_climbing'
    skitouring = 'skitouring'
    other = 'other'


class EventTypes(SafeStrEnum):
    avalanche = 'avalanche'
    stone_ice_fall = 'stone_ice_fall'
    ice_cornice_collapse = 'ice_cornice_collapse'
    person_fall = 'person_fall'
    crevasse_fall = 'crevasse_fall'
    physical_failure = 'physical_failure'
    injury_without_fall = 'injury_without_fall'
    blocked_person = 'blocked_person'
    weather_event = 'weather_event'
    safety_operation = 'safety_operation'
    critical_situation = 'critical_situation'
    other = 'other'


class AuthorStatuses(SafeStrEnum):
    primary_impacted = 'primary_impacted'
    secondary_impacted = 'secondary_impacted'
    internal_witness = 'internal_witness'
    external_witness = 'external_witness'


class ActivityRates(SafeStrEnum):
    activity_rate_y5 = 'activity_rate_y5'
    activity_rate_m2 = 'activity_rate_m2'
    activity_rate_w1 = 'activity_rate_w1'


class Genders(SafeStrEnum):
    male = 'male'
    female = 'female'


class PreviousInjuries(SafeStrEnum):
    no = 'no'
    previous_injuries_2 = 'previous_injuries_2'
    previous_injuries_3 = 'previous_injuries_3'


class Severities(SafeStrEnum):
    severity_no = 'severity_no'
    d1_to_3d = '1d_to_3d'
    d4_to_1m = '4d_to_1m'
    m1_to_3m = '1m_to_3m'
    more_than_3m = 'more_than_3m'


class Autonomies(SafeStrEnum):
    non_autonomous = 'non_autonomous'
    autonomous = 'autonomous'
    expert = 'expert'


class Supervision(SafeStrEnum):
    no_supervision = 'no_supervision'
    federal_supervision = 'federal_supervision'
    professional_supervision = 'professional_supervision'


class Qualification(SafeStrEnum):
    federal_supervisor = 'federal_supervisor'
    federal_trainer = 'federal_trainer'
    professional_diploma = 'professional_diploma'


class AvalancheLevels(SafeStrEnum):
    level_1 = 'level_1'
    level_2 = 'level_2'
    level_3 = 'level_3'
    level_4 = 'level_4'
    level_5 = 'level_5'
    level_na = 'level_na'


class AvalancheSlopes(SafeStrEnum):
    slope_lt_30 = 'slope_lt_30'
    slope_30_35 = 'slope_30_35'
    slope_35_40 = 'slope_35_40'
    slope_40_45 = 'slope_40_45'
    slope_gt_45 = 'slope_gt_45'


class SlacklineTypes(SafeStrEnum):
    slackline = 'slackline'
    highline = 'highline'
    waterline = 'waterline'


class CoverageTypes(SafeStrEnum):
    fr_idf = 'fr-idf'
    fr_ne = 'fr-ne'
    fr_nw = 'fr-nw'
    fr_se = 'fr-se'
    fr_sw = 'fr-sw'
