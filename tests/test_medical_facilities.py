from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.apis.v1.facility_routers import medical_facility_map_config
from app.core import config
from app.facilities.providers import (
    DevelopmentMedicalFacilitySearchProvider,
    KakaoLocalMedicalFacilitySearchProvider,
    MedicalFacilitySearchError,
    NemcEmergencyFacilitySearchProvider,
    get_medical_facility_search_provider,
)
from app.services.facilities import MedicalFacilityService

ROOT = Path(__file__).resolve().parents[1]


def test_facility_map_keeps_user_location_at_center_after_fitting_bounds() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    fit_bounds = script.index("map.setBounds(bounds)")
    restore_user_center = script.index("map.setCenter(center)", fit_bounds)

    assert restore_user_center > fit_bounds


def test_geolocation_retries_position_unavailable_with_high_accuracy() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "getCurrentPositionWithRetry" in script
    assert "maximumAge: 300000" in script
    assert "enableHighAccuracy: true" in script
    assert "if (![2, 3].includes(firstError.code))" in script


def test_address_search_is_available_when_browser_location_fails() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "libraries=services" in script
    assert "dapi.kakao.com/v2/maps/sdk.js" not in html
    assert 'api("/medical-facilities/map-config")' in script
    assert 'id="facility-address-form"' in html
    assert "coordinatesForAddress" in script
    assert "geocoder.addressSearch" in script
    assert "DEFAULT_FACILITY_LOCATION" not in script
    assert "기본 위치" not in script
    assert 'autocomplete="off"' in html
    assert 'input.value = ""' in script
    assert '$("#facility-address-form").hidden = false' in script
    assert '$("#emergency-address-form").hidden = false' in script


def test_new_or_failed_search_clears_old_map_and_uses_search_reference_label() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "function resetFacilitySearchUi(target)" in script
    assert "clearFacilityMapMarkers(target)" in script
    assert "map.hidden = true" in script
    assert script.count('resetFacilitySearchUi("medical")') >= 4
    assert script.count('resetFacilitySearchUi("emergency")') >= 4
    assert script.count('"검색 기준 위치"') >= 2
    assert 'href="tel:119"' in html


def test_urgent_guidance_uses_official_emergency_facility_endpoint() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="emergency-facility-search"' in html
    assert 'id="find-nearby-emergency"' not in html
    assert 'const isUrgent = reason === "URGENT_MEDICAL_ATTENTION"' in script
    assert '$("#urgent-guidance-actions").hidden = !isUrgent' in script
    assert "api(`/emergency-facilities/nearby?${params.toString()}`)" in script


@pytest.mark.asyncio
async def test_development_provider_returns_deterministic_facilities() -> None:
    provider = DevelopmentMedicalFacilitySearchProvider()

    results = await provider.search(latitude=37.5, longitude=127.0, radius_meters=5000)

    assert len(results) == 3
    assert all(item.department_hint for item in results)
    assert all(item.distance_meters is not None for item in results)
    assert provider.provider_kind == "development"
    assert provider.data_source == "development_mock"


def test_kakao_category_name_parsing_extracts_last_segment() -> None:
    document = {
        "place_name": "OO의원",
        "category_name": "의료,건강 > 병원 > 내과",
        "address_name": "서울 강남구",
        "road_address_name": "",
        "phone": "02-000-0000",
        "distance": "350",
        "place_url": "https://place.map.kakao.com/1",
        "x": "127.027",
        "y": "37.497",
        "id": "1",
    }

    result = KakaoLocalMedicalFacilitySearchProvider._to_facility_result(document)

    assert result.department_hint == "내과"
    assert result.name == "OO의원"
    assert result.distance_meters == 350
    assert result.latitude == pytest.approx(37.497)
    assert result.longitude == pytest.approx(127.027)


def test_kakao_category_name_without_subcategory_has_no_department_hint() -> None:
    document = {"place_name": "이름만 있는 곳", "category_name": "병원", "x": "127.0", "y": "37.5", "id": "2"}

    result = KakaoLocalMedicalFacilitySearchProvider._to_facility_result(document)

    assert result.department_hint is None


def test_kakao_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "")

    with pytest.raises(MedicalFacilitySearchError, match="KAKAO_REST_API_KEY"):
        KakaoLocalMedicalFacilitySearchProvider()


def test_map_keys_are_environment_driven_and_not_embedded_in_html() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "appkey=" not in html
    assert "MEDICAL_FACILITY_SEARCH_PROVIDER=" in example
    assert "KAKAO_REST_API_KEY=" in example
    assert "KAKAO_JAVASCRIPT_KEY=" in example


@pytest.mark.asyncio
async def test_map_config_exposes_only_configured_public_javascript_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "KAKAO_JAVASCRIPT_KEY", "public-js-test-key")

    response = await medical_facility_map_config(object())

    assert response["data"] == {"enabled": True, "javascript_key": "public-js-test-key"}
    assert "KAKAO_REST_API_KEY" not in str(response)


def test_unsupported_provider_setting_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MEDICAL_FACILITY_SEARCH_PROVIDER", "not-a-real-provider")

    with pytest.raises(MedicalFacilitySearchError, match="지원하지 않는"):
        get_medical_facility_search_provider()


@pytest.mark.asyncio
async def test_service_nearby_wraps_provider_results_with_disclaimer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MEDICAL_FACILITY_SEARCH_PROVIDER", "development")

    payload = await MedicalFacilityService().nearby(latitude=37.5, longitude=127.0, radius_meters=3000)

    assert payload["provider_kind"] == "development"
    assert payload["retrieved_radius_meters"] == 3000
    assert "진단" in payload["disclaimer"]
    assert len(payload["facilities"]) == 3
    # department_hint는 응답 데이터에는 계속 포함됩니다(화면에 안 보여주는 것은 프론트 책임).
    assert all("department_hint" in facility for facility in payload["facilities"])


class _FakeKakaoResponse:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = documents

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"documents": self._documents}


class _FakeKakaoAsyncClient:
    """실제 네트워크 호출 없이 카카오 응답을 흉내 내는 테스트용 httpx.AsyncClient 대체품입니다."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeKakaoAsyncClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info
        return None

    async def get(self, url: str, *, headers: dict[str, str], params: dict[str, str]) -> _FakeKakaoResponse:
        del url, headers
        query = params["query"]
        if query == "당뇨":
            documents = [
                {
                    "id": "1",
                    # 장소 이름에 검색어나 "내과"가 없어도 카카오가 당뇨 관련 병원으로 반환할 수 있습니다.
                    "place_name": "튼튼의원",
                    "category_name": "의료,건강 > 병원 > 내과",
                    "address_name": "서울 중구",
                    "road_address_name": "",
                    "phone": "02-000-0000",
                    "distance": "300",
                    "place_url": "https://place.map.kakao.com/1",
                    "x": "126.978",
                    "y": "37.566",
                },
                {
                    # "내과" 키워드가 텍스트 매칭으로 걸러내는 치과 사례 — 결과에서 제외되어야 합니다.
                    "id": "2",
                    "place_name": "시청서울구강내과치과의원",
                    "category_name": "의료,건강 > 병원 > 치과",
                    "address_name": "서울 중구",
                    "road_address_name": "",
                    "phone": "02-000-0001",
                    "distance": "115",
                    "place_url": "https://place.map.kakao.com/2",
                    "x": "126.977",
                    "y": "37.567",
                },
            ]
        else:
            documents = []
        return _FakeKakaoResponse(documents)


@pytest.mark.asyncio
async def test_kakao_provider_searches_diabetes_without_requiring_internal_medicine_in_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 검색어는 "당뇨"만 사용하며, 장소 이름에 "당뇨"나 "내과"가 없어도 카카오 검색 결과를 유지합니다.
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(config, "MEDICAL_FACILITY_SEARCH_KEYWORDS", "당뇨")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeKakaoAsyncClient)

    provider = KakaoLocalMedicalFacilitySearchProvider()
    results = await provider.search(latitude=37.5665, longitude=126.9780, radius_meters=5000)

    assert [item.name for item in results] == ["튼튼의원"]
    assert all("치과" not in item.name for item in results)


class _FakeNemcResponse:
    content = """<?xml version='1.0' encoding='UTF-8'?>
    <response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header><body><items><item>
      <dutyName>서울응급의료센터</dutyName><dutyAddr>서울 중구 테스트로 1</dutyAddr>
      <dutyTel3>02-123-4567</dutyTel3><dutyEmclsName>지역응급의료센터</dutyEmclsName>
      <latitude>37.5665</latitude><longitude>126.9780</longitude>
    </item></items></body></response>""".encode()

    def raise_for_status(self) -> None:
        return None


class _FakeNemcAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeNemcAsyncClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        del exc_info

    async def get(self, *args: object, **kwargs: object) -> _FakeNemcResponse:
        del args, kwargs
        return _FakeNemcResponse()


@pytest.mark.asyncio
async def test_nemc_provider_maps_official_emergency_facility_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "NEMC_SERVICE_KEY", "test-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeNemcAsyncClient)

    results = await NemcEmergencyFacilitySearchProvider().search(
        latitude=37.5665, longitude=126.9780, radius_meters=10000
    )

    assert len(results) == 1
    assert results[0].name == "서울응급의료센터"
    assert results[0].phone == "02-123-4567"
    assert results[0].department_hint == "지역응급의료센터"


def test_nemc_service_key_accepts_url_encoded_value() -> None:
    source = (ROOT / "app/facilities/providers.py").read_text(encoding="utf-8")

    assert '"serviceKey": unquote(config.NEMC_SERVICE_KEY)' in source
