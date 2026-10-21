from dataclasses import dataclass

from models.address_types import AddressTypeCategory


@dataclass(slots=True, frozen=True)
class SystemAddressTypeDefinition:
    code: str
    category: AddressTypeCategory
    name: str
    short_name: str | None
    sort_order: int


SYSTEM_ADDRESS_TYPES = (
    SystemAddressTypeDefinition(
        code="country",
        category=AddressTypeCategory.COUNTRY,
        name="Страна",
        short_name=None,
        sort_order=10,
    ),
    SystemAddressTypeDefinition(
        code="region",
        category=AddressTypeCategory.REGION,
        name="Регион",
        short_name=None,
        sort_order=20,
    ),
    SystemAddressTypeDefinition(
        code="city",
        category=AddressTypeCategory.LOCALITY,
        name="Город",
        short_name="г.",
        sort_order=30,
    ),
    SystemAddressTypeDefinition(
        code="settlement",
        category=AddressTypeCategory.LOCALITY,
        name="Посёлок",
        short_name="пос.",
        sort_order=40,
    ),
    SystemAddressTypeDefinition(
        code="village",
        category=AddressTypeCategory.LOCALITY,
        name="Село",
        short_name="с.",
        sort_order=50,
    ),
    SystemAddressTypeDefinition(
        code="district",
        category=AddressTypeCategory.AREA,
        name="Район",
        short_name="р-н",
        sort_order=60,
    ),
    SystemAddressTypeDefinition(
        code="municipal_district",
        category=AddressTypeCategory.AREA,
        name="Муниципальный округ",
        short_name="м.о.",
        sort_order=70,
    ),
    SystemAddressTypeDefinition(
        code="microdistrict",
        category=AddressTypeCategory.TERRITORY,
        name="Микрорайон",
        short_name="мкр.",
        sort_order=71,
    ),
    SystemAddressTypeDefinition(
        code="quarter",
        category=AddressTypeCategory.TERRITORY,
        name="Квартал",
        short_name="кв-л",
        sort_order=72,
    ),
    SystemAddressTypeDefinition(
        code="snt_territory",
        category=AddressTypeCategory.TERRITORY,
        name="Территория СНТ",
        short_name="тер. СНТ",
        sort_order=73,
    ),
    SystemAddressTypeDefinition(
        code="tsn_territory",
        category=AddressTypeCategory.TERRITORY,
        name="Территория ТСН",
        short_name="тер. ТСН",
        sort_order=74,
    ),
    SystemAddressTypeDefinition(
        code="dnt_territory",
        category=AddressTypeCategory.TERRITORY,
        name="Территория ДНТ",
        short_name="тер. ДНТ",
        sort_order=75,
    ),
    SystemAddressTypeDefinition(
        code="industrial_zone",
        category=AddressTypeCategory.TERRITORY,
        name="Промышленная зона",
        short_name="промзона",
        sort_order=76,
    ),
    SystemAddressTypeDefinition(
        code="territory",
        category=AddressTypeCategory.TERRITORY,
        name="Территория",
        short_name="тер.",
        sort_order=77,
    ),
    SystemAddressTypeDefinition(
        code="street",
        category=AddressTypeCategory.THOROUGHFARE,
        name="Улица",
        short_name="ул.",
        sort_order=80,
    ),
    SystemAddressTypeDefinition(
        code="avenue",
        category=AddressTypeCategory.THOROUGHFARE,
        name="Проспект",
        short_name="пр-т",
        sort_order=90,
    ),
    SystemAddressTypeDefinition(
        code="lane",
        category=AddressTypeCategory.THOROUGHFARE,
        name="Переулок",
        short_name="пер.",
        sort_order=100,
    ),
)
