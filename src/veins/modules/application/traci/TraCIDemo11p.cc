#include "veins/modules/application/traci/TraCIDemo11p.h" // 헤더 파일 포함
#include "veins/modules/application/traci/TraCIDemo11pMessage_m.h" // 메시지 구조 정의 파일 포함

using namespace veins; // veins 네임스페이스 사용

Define_Module(veins::TraCIDemo11p); // 이 클래스를 OMNeT++ 모듈로 등록

// 모듈 초기화 함수
void TraCIDemo11p::initialize(int stage)
{
    DemoBaseApplLayer::initialize(stage); // 부모 클래스의 초기화 수행
    if (stage == 0) { // 초기화 첫 단계에서 변수 설정
        sentMessage = false; // 메시지 전송 여부 초기화
        lastDroveAt = simTime(); // 마지막 주행 시간 초기화 (현재 시간)
        currentSubscribedServiceId = -1; // 구독 중인 서비스 ID 초기화 (없음)
    }
}

// 서비스 광고(WSA)를 받았을 때 처리하는 함수
void TraCIDemo11p::onWSA(DemoServiceAdvertisment* wsa)
{
    if (currentSubscribedServiceId == -1) { // 아직 구독 중인 서비스가 없다면
        mac->changeServiceChannel(static_cast<Channel>(wsa->getTargetChannel())); // 채널을 광고된 채널로 변경
        currentSubscribedServiceId = wsa->getPsid(); // 구독 ID 저장

        // 중요: 서비스 ID가 다르면 기존 서비스를 멈추고 새 서비스 시작
        if (currentOfferedServiceId != wsa->getPsid()) {
            if (currentOfferedServiceId != -1) {
                stopService(); // 이미 다른 서비스가 켜져 있을 때만 안전하게 끄기
            }
              // 주의: 여기서 startService가 중복 호출되면 런타임 에러 발생
            startService(static_cast<Channel>(wsa->getTargetChannel()), wsa->getPsid(), "Mirrored Traffic Service");
        }
    }
}

// 일반 데이터 메시지(WSM)를 받았을 때 처리하는 함수 - GUI 변경, 경로 변경, 재전송
void TraCIDemo11p::onWSM(BaseFrame1609_4* frame)
{
    // 받은 프레임을 TraCIDemo11pMessage 타입으로 변환
    TraCIDemo11pMessage* wsm = check_and_cast<TraCIDemo11pMessage*>(frame);

    // 메시지를 받으면 차량 아이콘 색상을 녹색(green)으로 변경
    findHost()->getDisplayString().setTagArg("i", 1, "green");

    // 도로 ID가 ':'로 시작하지 않으면(정상 도로면), 받은 데이터에 적힌 도로로 경로 변경
    if (mobility->getRoadId()[0] != ':') traciVehicle->changeRoute(wsm->getDemoData(), 9999);

    if (!sentMessage) { // 아직 메시지를 재전송하지 않았다면
        sentMessage = true; // 전송 상태로 변경
        // 2초 뒤에(약간의 랜덤 지연 포함) 받은 메시지를 다시 주변에 전송 예약
        wsm->setSenderAddress(myId); // 보낸 사람 주소를 내 ID로 설정
        wsm->setSerial(3); // 시리얼 번호 설정 = 메시지의 생명 주기 = 재전송 가능 횟수
        scheduleAt(simTime() + 2 + uniform(0.01, 0.2), wsm->dup()); // 복사본 전송 예약 // 메시지 예약1
    }
}

// 예약된 메시지(Self Message) 시간이 되었을 때 처리하는 함수
void TraCIDemo11p::handleSelfMsg(cMessage* msg)
{
    if (TraCIDemo11pMessage* wsm = dynamic_cast<TraCIDemo11pMessage*>(msg)) {
        sendDown(wsm->dup()); // 하위 계층(물리 채널)으로 메시지 전송
        wsm->setSerial(wsm->getSerial() + 1); // 재전송 횟수 증가

        if (wsm->getSerial() >= 3) { // 3번 이상 보냈다면
            stopService(); // 서비스 종료
            delete (wsm); // 메시지 메모리 삭제
        }
        else { // 아직 더 보내야 한다면
            scheduleAt(simTime() + 1, wsm); // 1초 뒤에 다시 보내도록 예약
        }
    }
    else {
        DemoBaseApplLayer::handleSelfMsg(msg); // 일반적인 셀프 메시지 처리
    }
}

// 매 순간 차량의 위치/상태가 업데이트될 때 실행되는 함수
void TraCIDemo11p::handlePositionUpdate(cObject* obj)
{
    DemoBaseApplLayer::handlePositionUpdate(obj); // 부모 클래스의 위치 업데이트 수행

    // 차량의 속도가 1미만(정지 상태)인지 확인
    if (mobility->getSpeed() < 1) {
        // 10초 이상 멈춰있고 메시지를 아직 안 보냈다면 (사고 상황 가정)
        if (simTime() - lastDroveAt >= 10 && sentMessage == false) {
            findHost()->getDisplayString().setTagArg("i", 1, "red"); // 차량 색상을 빨간색으로 변경
            sentMessage = true; // 메시지 발송 상태로 변경

            TraCIDemo11pMessage* wsm = new TraCIDemo11pMessage(); // 새 메시지 생성
            populateWSM(wsm); // 기본 통신 정보 채우기
            // 현재 차량이 있는 도로 ID를 데이터에 삽입!
            wsm->setDemoData(mobility->getRoadId().c_str());

            if (dataOnSch) { // 서비스 채널을 사용하는 설정이라면
                // 여기서 서비스를 시작하고 예약 전송
                // 주의: 여기서도 startService 중복 호출 에러 가능성 있음
                if (currentOfferedServiceId == -1) { // 실행 중인 서비스가 없을 때만 켜기
                    startService(Channel::sch2, 42, "Traffic Information Service");
                }
                scheduleAt(computeAsynchronousSendingTime(1, ChannelType::service), wsm); // 메시지 예약2
            }
            else { // 채널 전환을 안 쓴다면
                sendDown(wsm); // 공용 채널(CCH)로 즉시 전송
            }
        }
    }
    else { // 차가 움직이고 있다면
        lastDroveAt = simTime(); // 마지막 주행 시간을 현재로 갱신
    }
}
