using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

/// <summary>
/// 360° 고정 카메라(서버)가 UDP로 보내는 사각지대 장애물 JSON을 수신하여
/// Anchor360 기준으로 큐브를 스폰한다. 기존 Go1ObstacleJsonReceiver(포트 5009)와 완전히 별개.
///
/// 사용법:
///  1) 빈 GameObject "Anchor360"을 만들고 실제 360 카메라의 가로 위치에 놓는다.
///     - +Z(파란 화살표)를 맵의 GO1 주행 방향에 맞춘다.  높이(y)는 상관없음(바닥으로 강제됨).
///  2) 이 컴포넌트를 Anchor360에 붙인다. (anchorTransform 비우면 자기 자신 사용)
///  3) listenPort=5010, obstaclePrefab(선택) 지정.
///  4) 큐브가 실제 장애물과 어긋나면 Inspector에서 yawOffsetDeg / invertX / distanceScale 조정.
/// </summary>
public class Anchor360ObstacleReceiver : MonoBehaviour
{   
    [Header("File Load (정적 환경용 / 슬라이스 시험용)")]
    [Tooltip("true면 UDP 대신 아래 JSON 파일을 읽어 큐브 생성.")]
    public bool loadFromFile = false;
    [Tooltip("Project에서 .json 파일을 여기로 끌어다 놓으면 됨.")]
    public TextAsset jsonFile;

    [Header("Network")]
    public int listenPort = 5010;                 // 기존 5009와 다른 포트

    [Header("Anchor")]
    [Tooltip("360 카메라 기준 오브젝트. 비우면 이 컴포넌트가 붙은 오브젝트를 사용.")]
    public Transform anchorTransform;

    [Header("Calibration (실측 보정용 손잡이)")]
    [Tooltip("큐브 전체가 회전돼 보이면 조정 (도).")]
    public float yawOffsetDeg = 0f;
    [Tooltip("좌우가 뒤집혀 보이면 체크.")]
    public bool invertX = false;
    [Tooltip("거리가 멀거나 가깝게 보이면 조정 (가로거리 배율).")]
    public float distanceScale = 1.0f;

    [Header("Floor")]
    [Tooltip("장애물은 바닥에 있으므로 큐브 높이를 이 y로 강제한다(맵 바닥 높이). 보통 0.")]
    public float floorWorldY = 0f;

    [Header("Cube")]
    public GameObject obstaclePrefab;             // 비우면 기본 Cube 생성
    public float minCubeSize = 0.15f;
    public float maxCubeSize = 3.0f;
    public float defaultCubeSize = 0.4f;          // size 없을 때
    [Tooltip("bbox 유래 크기가 커서 여유를 주고 싶으면 배율.")]
    public float sizeMultiplier = 1.0f;

    [Header("Tag / Layer (기존과 동일하게 NavMesh/ML-Agent가 인식하도록)")]
    public bool assignObstacleTagAndLayer = true;
    public string obstacleTagName = "Obstacle";
    public string obstacleLayerName = "Obstacle";

    [Header("Coordinate Label (큐브 위에 x, y, z 표시)")]
    [Tooltip("큐브 위에 좌표 글자를 띄운다.")]
    public bool showCoordLabel = true;
    [Tooltip("false = 360 서버가 보낸 앵커 좌표(m, +x 오른쪽 · +y 위 · +z 정면 — 탐지 화면 글자와 같은 값). true = 이 씬의 월드 좌표.")]
    public bool labelUseUnityWorld = false;
    [Tooltip("글자 크기(월드 단위). 너무 작거나 크면 조정.")]
    public float labelCharacterSize = 0.05f;
    public int labelFontSize = 48;
    public Color labelColor = Color.green;
    [Tooltip("큐브 윗면에서 글자까지 높이(m).")]
    public float labelHeightOffset = 0.15f;

    [Header("Debug")]
    public bool printReceivedJson = false;

    // ---- JSON 구조 — 통합데이터규약 v2 (서버 anchor360_live.py · 2026-10-27 전환) ----
    // v2 이름: label · position · ground_dist_m · size_m · bbox · confidence (+ 패킷 머리 schema_version · source_id)
    // 옛 v1 이름(name · pos3d · dist_m · size · bbox_xyxy · conf)도 받는다 — 서버를 바꾸는 동안 큐브가 끊기지 않게.
    // JsonUtility 는 빠진 중첩 객체를 null 이 아니라 빈 객체로 만든다 → v2/v1 판정은 label 문자열로 한다.
    [Serializable] public class Pos3D { public float x, y, z; }
    [Serializable] public class Size  { public float w, h, d; }
    [Serializable]
    public class Det360
    {
        public int id;
        public string group;
        public bool ground_clipped;
        // v2
        public string label;
        public float confidence;
        public float[] bbox;
        public Pos3D position;
        public float ground_dist_m;
        public Size size_m;
        // v1 (옛 서버)
        public string name;
        public Pos3D pos3d;
        public float dist_m;
        public Size size;
        public int[] bbox_xyxy;

        public bool IsV2   => !string.IsNullOrEmpty(label);
        public string Label => IsV2 ? label : name;
        public Pos3D Pos    => IsV2 ? position : pos3d;
        public Size Dim     => IsV2 ? size_m : size;
    }
    [Serializable]
    public class Anchor360Packet
    {
        public string schema_version;  // v2: "2.0"
        public string source_id;       // v2: 보낸 쪽 (v1 의 camera_id 자리)
        public string timestamp;
        public string emitted_at;
        public string camera_id;       // v1
        public string frame;           // v1
        public Det360[] detections;

        public string Source => !string.IsNullOrEmpty(source_id) ? source_id : camera_id;
    }

    // ---- UDP ----
    private UdpClient udp;
    private Thread rxThread;
    private volatile bool running = false;
    private readonly object lockObj = new object();
    private string latestJson = null;            // 최신 패킷만 유지(스냅샷)

    // ---- 스폰된 큐브 ----
    private readonly List<GameObject> spawned = new List<GameObject>();
    private readonly List<Transform> labels = new List<Transform>();   // 카메라를 향하게 돌릴 좌표 글자
    private GameObject root;
    private Font labelFont;

    void Start()
    {
        if (anchorTransform == null) anchorTransform = transform;
        root = new GameObject("Anchor360_Obstacles");
        if (loadFromFile) LoadFromFileOnce();
        else StartReceiver();
    }

    void LoadFromFileOnce()
    {
        if (jsonFile == null) { Debug.LogError("[Anchor360] jsonFile 슬롯이 비어있음"); return; }
        try {
            var pkt = JsonUtility.FromJson<Anchor360Packet>(jsonFile.text);
            if (pkt?.detections == null) { Debug.LogWarning("[Anchor360] 파싱 실패/빈 detections"); return; }
            if (printReceivedJson) Debug.Log("[Anchor360] FILE: " + jsonFile.text);
            RebuildObstacles(pkt);
            Debug.Log($"[Anchor360] '{jsonFile.name}'에서 {pkt.detections.Length}개 로드");
        } catch (System.Exception e) { Debug.LogError("[Anchor360] 로드 실패: " + e.Message); }
    }

    void StartReceiver()
    {
        try
        {
            udp = new UdpClient(listenPort);
            running = true;
            rxThread = new Thread(ReceiveLoop) { IsBackground = true };
            rxThread.Start();
            Debug.Log($"[Anchor360] UDP {listenPort} 수신 시작");
        }
        catch (Exception e)
        {
            Debug.LogError($"[Anchor360] 포트 {listenPort} 열기 실패: {e.Message}");
        }
    }

    void ReceiveLoop()
    {
        IPEndPoint any = new IPEndPoint(IPAddress.Any, 0);
        while (running)
        {
            try
            {
                byte[] data = udp.Receive(ref any);   // blocking
                string s = Encoding.UTF8.GetString(data);
                lock (lockObj) { latestJson = s; }    // 최신만 보관
            }
            catch (Exception) { /* 소켓 종료 시 무시 */ }
        }
    }

    void Update()
    {
        string json = null;
        lock (lockObj) { if (latestJson != null) { json = latestJson; latestJson = null; } }
        if (json == null) return;

        if (printReceivedJson) Debug.Log("[Anchor360] RX: " + json);

        Anchor360Packet pkt;
        try { pkt = JsonUtility.FromJson<Anchor360Packet>(json); }
        catch (Exception e) { Debug.LogWarning("[Anchor360] JSON 파싱 실패: " + e.Message); return; }
        if (pkt == null || pkt.detections == null) return;

        RebuildObstacles(pkt);   // 스냅샷: 이전 것 제거 후 새로 생성
    }

    void RebuildObstacles(Anchor360Packet pkt)
    {
        // 이전 360 큐브 전부 제거(스냅샷 방식 → 사라진 장애물 자동 제거)
        foreach (var go in spawned) if (go != null) Destroy(go);
        spawned.Clear();
        labels.Clear();

        Quaternion yawFix = Quaternion.Euler(0f, yawOffsetDeg, 0f);

        foreach (var det in pkt.detections)
        {
            var p3 = det.Pos;
            if (p3 == null) continue;

            // anchor 로컬 좌표(가로만 사용). y는 뒤에서 바닥으로 강제.
            float lx = p3.x * (invertX ? -1f : 1f) * distanceScale;
            float lz = p3.z * distanceScale;
            Vector3 local = yawFix * new Vector3(lx, 0f, lz);

            Vector3 world = anchorTransform.TransformPoint(local);

            // 크기
            Vector3 scale = ComputeScale(det.Dim);
            // 바닥에 세우기: 높이는 맵 바닥으로 강제, 큐브 중심은 절반 위로
            Vector3 pos = new Vector3(world.x, floorWorldY + scale.y * 0.5f, world.z);

            GameObject obj = (obstaclePrefab != null)
                ? Instantiate(obstaclePrefab)
                : GameObject.CreatePrimitive(PrimitiveType.Cube);
            obj.name = $"Obs360_{det.Label}_{det.id}";
            obj.transform.SetParent(root.transform, true);
            obj.transform.position = pos;
            obj.transform.localScale = scale;
            if (obj.GetComponent<Collider>() == null) obj.AddComponent<BoxCollider>();
            ApplyTagAndLayer(obj);

            spawned.Add(obj);

            if (showCoordLabel)
            {
                Vector3 shown = labelUseUnityWorld ? pos : new Vector3(p3.x, p3.y, p3.z);
                var top = new Vector3(pos.x, pos.y + scale.y * 0.5f + labelHeightOffset, pos.z);
                SpawnLabel($"{det.Label}\n{FormatXyz(shown)}", top);
            }
        }
    }

    static string FormatXyz(Vector3 v)
    {
        const string f = "+0.00;-0.00;0.00";
        return $"x={v.x.ToString(f)} y={v.y.ToString(f)} z={v.z.ToString(f)}";
    }

    void SpawnLabel(string text, Vector3 worldPos)
    {
        if (labelFont == null)
        {
            // Unity 2022.2+ 는 LegacyRuntime.ttf, 그 전 판은 Arial.ttf 가 내장 글꼴이다
            try { labelFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf"); } catch { }
            if (labelFont == null) { try { labelFont = Resources.GetBuiltinResource<Font>("Arial.ttf"); } catch { } }
            if (labelFont == null) { Debug.LogWarning("[Anchor360] 내장 글꼴을 못 찾아 좌표 글자를 끈다."); showCoordLabel = false; return; }
        }
        // 큐브의 자식으로 두면 큐브 크기(scale)에 글자가 찌그러지므로 root 아래에 따로 둔다
        var go = new GameObject("Obs360_Label");
        go.transform.SetParent(root.transform, false);
        go.transform.position = worldPos;
        var tm = go.AddComponent<TextMesh>();
        tm.text = text;
        tm.font = labelFont;
        tm.fontSize = labelFontSize;
        tm.characterSize = labelCharacterSize;
        tm.anchor = TextAnchor.LowerCenter;
        tm.alignment = TextAlignment.Center;
        tm.color = labelColor;
        go.GetComponent<MeshRenderer>().sharedMaterial = labelFont.material;
        spawned.Add(go);
        labels.Add(go.transform);
    }

    void LateUpdate()
    {
        // 좌표 글자가 항상 카메라 쪽을 보게 한다(빌보드)
        if (labels.Count == 0) return;
        var cam = Camera.main;
        if (cam == null) return;
        Vector3 c = cam.transform.position;
        foreach (var t in labels)
            if (t != null) t.rotation = Quaternion.LookRotation(t.position - c);
    }

    Vector3 ComputeScale(Size s)
    {
        float w = defaultCubeSize, h = defaultCubeSize, d = defaultCubeSize;
        if (s != null && s.w > 0f) { w = s.w; h = (s.h > 0f ? s.h : s.w); d = (s.d > 0f ? s.d : s.w); }
        w *= sizeMultiplier; h *= sizeMultiplier; d *= sizeMultiplier;
        w = Mathf.Clamp(w, minCubeSize, maxCubeSize);
        h = Mathf.Clamp(h, minCubeSize, maxCubeSize);
        d = Mathf.Clamp(d, minCubeSize, maxCubeSize);
        return new Vector3(w, h, d);
    }

    void ApplyTagAndLayer(GameObject obj)
    {
        if (!assignObstacleTagAndLayer) return;
        try { if (!string.IsNullOrEmpty(obstacleTagName)) obj.tag = obstacleTagName; }
        catch { Debug.LogWarning($"[Anchor360] Tag '{obstacleTagName}' 없음. Tags & Layers에 추가 필요."); }
        if (!string.IsNullOrEmpty(obstacleLayerName))
        {
            int layer = LayerMask.NameToLayer(obstacleLayerName);
            if (layer >= 0) obj.layer = layer;
            else Debug.LogWarning($"[Anchor360] Layer '{obstacleLayerName}' 없음. Tags & Layers에 추가 필요.");
        }
    }

    void OnDestroy()  { StopReceiver(); }
    void OnApplicationQuit() { StopReceiver(); }
    void StopReceiver()
    {
        running = false;
        try { udp?.Close(); } catch { }
        try { rxThread?.Join(200); } catch { }
    }
}
