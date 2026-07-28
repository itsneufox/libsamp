#include <Server/Components/Timers/timers.hpp>
#include <sdk.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <new>

namespace
{
constexpr int kRpcDisplayGameText = 73;
constexpr StringView kCommand = "/rpc73replace";
constexpr int32_t kDisplayTimeMs = 5000;
constexpr int kReplacementDelayMs = 350;
constexpr char kFirstText[] = "RPC73_STYLE5_FIRST";
constexpr char kReplacementText[] = "RPC73_STYLE3_SECOND";
constexpr char kFirstPayloadHex[] =
	"05000000881300001200000052504337335f5354594c45355f4649525354";
constexpr char kReplacementPayloadHex[] =
	"03000000881300001300000052504337335f5354594c45335f5345434f4e44";

// STATIC_037:
// SA-MP 0.3.7-R5, SHA256
// b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
// RPC 73 at samp.dll+0x198F0 reads int32 style, int32 time, int32 byte
// length, and the raw text bytes. Its call at samp.dll+0x199C8 enters
// CGame::DisplayGameText at samp.dll+0xA0CE0, which first executes GTA
// opcode 0x00BE (text_clear_all) through the descriptor at
// samp.dll+0xEC724.
//
// These are closed payloads. Command/player data cannot influence any byte.
constexpr std::array<uint8_t, 30> kFirstPayload {
	0x05, 0x00, 0x00, 0x00,
	0x88, 0x13, 0x00, 0x00,
	0x12, 0x00, 0x00, 0x00,
	0x52, 0x50, 0x43, 0x37, 0x33, 0x5F, 0x53, 0x54, 0x59,
	0x4C, 0x45, 0x35, 0x5F, 0x46, 0x49, 0x52, 0x53, 0x54,
};

constexpr std::array<uint8_t, 31> kReplacementPayload {
	0x03, 0x00, 0x00, 0x00,
	0x88, 0x13, 0x00, 0x00,
	0x13, 0x00, 0x00, 0x00,
	0x52, 0x50, 0x43, 0x37, 0x33, 0x5F, 0x53, 0x54, 0x59,
	0x4C, 0x45, 0x33, 0x5F, 0x53, 0x45, 0x43, 0x4F, 0x4E, 0x44,
};

constexpr uint32_t readLittleEndian32(const uint8_t* data)
{
	return static_cast<uint32_t>(data[0])
		| (static_cast<uint32_t>(data[1]) << 8u)
		| (static_cast<uint32_t>(data[2]) << 16u)
		| (static_cast<uint32_t>(data[3]) << 24u);
}

template <std::size_t PayloadSize, std::size_t TextSize>
constexpr bool payloadMatches(
	const std::array<uint8_t, PayloadSize>& payload,
	int32_t style,
	int32_t timeMs,
	const char (&text)[TextSize])
{
	if (PayloadSize != 12u + TextSize - 1u
		|| readLittleEndian32(payload.data()) != static_cast<uint32_t>(style)
		|| readLittleEndian32(payload.data() + 4u) != static_cast<uint32_t>(timeMs)
		|| readLittleEndian32(payload.data() + 8u) != TextSize - 1u)
	{
		return false;
	}
	for (std::size_t index = 0; index + 1u < TextSize; ++index)
	{
		if (payload[12u + index] != static_cast<uint8_t>(text[index]))
		{
			return false;
		}
	}
	return true;
}

static_assert(kReplacementDelayMs > 0);
static_assert(kReplacementDelayMs < kDisplayTimeMs);
static_assert(payloadMatches(kFirstPayload, 5, kDisplayTimeMs, kFirstText));
static_assert(payloadMatches(
	kReplacementPayload, 3, kDisplayTimeMs, kReplacementText));

class Rpc73GameTextFixture;

class ReplacementTimer final : public TimerTimeOutHandler
{
public:
	ReplacementTimer(
		Rpc73GameTextFixture& owner,
		int playerID,
		uint32_t generation)
		: owner_(owner)
		, playerID_(playerID)
		, generation_(generation)
	{
	}

	void timeout(ITimer& timer) override;

	void free(ITimer&) override
	{
		delete this;
	}

private:
	Rpc73GameTextFixture& owner_;
	int playerID_;
	uint32_t generation_;
};

class Rpc73GameTextFixture final
	: public IComponent
	, public PlayerTextEventHandler
	, public PlayerConnectEventHandler
{
public:
	PROVIDE_UID(0x5250433733524550);

	~Rpc73GameTextFixture() override
	{
		cancelAll();
		detach();
	}

	StringView componentName() const override
	{
		return "RPC73 GameText replacement fixture";
	}

	SemanticVersion componentVersion() const override
	{
		return SemanticVersion(0, 1, 0, 0);
	}

	void onLoad(ICore* core) override
	{
		core_ = core;
		if (core_ == nullptr)
		{
			return;
		}

		core_->getPlayers().getPlayerTextDispatcher().addEventHandler(this);
		core_->getPlayers().getPlayerConnectDispatcher().addEventHandler(this);
		attached_ = true;
		core_->printLn(
			"[rpc73_gametext_fixture] loaded command=/rpc73replace rpc=73 "
			"delay_ms=%d dispatchEvents=0 channel=SyncRPC",
			kReplacementDelayMs);
	}

	void onInit(IComponentList* components) override
	{
		timers_ = components == nullptr
			? nullptr
			: components->queryComponent<ITimersComponent>();
		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc73_gametext_fixture] timers_component=%s",
				timers_ == nullptr ? "missing" : "ready");
		}
	}

	void onFree(IComponent* component) override
	{
		if (component == timers_)
		{
			cancelAll();
			timers_ = nullptr;
		}
	}

	void free() override
	{
		delete this;
	}

	void reset() override
	{
		cancelAll();
		fired_.fill(false);
	}

	/// Equivalent callback contract:
	/// https://open.mp/docs/scripting/callbacks/OnPlayerDisconnect
	void onPlayerDisconnect(IPlayer& player, PeerDisconnectReason) override
	{
		const int playerID = player.getID();
		if (!validPlayerID(playerID))
		{
			return;
		}
		cancelPending(playerID);
		fired_[static_cast<std::size_t>(playerID)] = false;
	}

	/// Equivalent callback contract:
	/// https://open.mp/docs/scripting/callbacks/OnPlayerCommandText
	bool onPlayerCommandText(IPlayer& player, StringView message) override
	{
		if (message != kCommand)
		{
			return false;
		}

		const int playerID = player.getID();
		if (!validPlayerID(playerID))
		{
			reject(player, "RPC73 fixture rejected an invalid player ID");
			return true;
		}

		const char* failure = eligibilityFailure(player);
		if (failure != nullptr)
		{
			reject(player, failure);
			return true;
		}
		if (timers_ == nullptr)
		{
			reject(player, "RPC73 fixture requires the Timers component");
			return true;
		}

		const std::size_t index = static_cast<std::size_t>(playerID);
		if (fired_[index] || pending_[index] != nullptr)
		{
			reject(
				player,
				"RPC73 fixture is one-shot per connection; reconnect to rerun");
			return true;
		}

		const uint32_t generation = bumpGeneration(index);
		ReplacementTimer* handler =
			new (std::nothrow) ReplacementTimer(*this, playerID, generation);
		if (handler == nullptr)
		{
			reject(player, "RPC73 fixture could not allocate its delay handler");
			return true;
		}

		ITimer* timer = nullptr;
		try
		{
			timer = timers_->create(
				handler, Milliseconds(kReplacementDelayMs), false);
		}
		catch (...)
		{
			// Do not permit allocation failures inside the timer component to
			// escape this component callback boundary.
			timer = nullptr;
		}
		if (timer == nullptr)
		{
			delete handler;
			reject(player, "RPC73 fixture could not create its delay timer");
			return true;
		}

		pending_[index] = timer;
		fired_[index] = true;

		const bool sent = sendPayload(
			player,
			"first",
			5,
			kFirstText,
			kFirstPayload,
			kFirstPayloadHex);
		if (!sent)
		{
			timer->kill();
			pending_[index] = nullptr;
			reject(
				player,
				"RPC73 first payload transport failed; inspect server log");
			return true;
		}

		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc73_gametext_fixture] scheduled player=%d "
				"replacement_delay_ms=%d generation=%u",
				playerID,
				kReplacementDelayMs,
				static_cast<unsigned>(generation));
		}
		player.sendClientMessage(
			Colour::White(),
			"RPC73 style 5 sent; fixed style 3 replacement scheduled.");
		return true;
	}

private:
	friend class ReplacementTimer;

	static bool validPlayerID(int playerID)
	{
		return playerID >= 0 && playerID < PLAYER_POOL_SIZE;
	}

	static const char* eligibilityFailure(const IPlayer& player)
	{
		if (player.isBot())
		{
			return "RPC73 fixture does not accept bots";
		}
		if (player.getClientVersion() != ClientVersion::ClientVersion_SAMP_037)
		{
			return "RPC73 fixture requires the SA-MP 0.3.7 protocol";
		}
		if (player.getState() == PlayerState_None)
		{
			return "RPC73 fixture requires an initialized player";
		}
		const PeerNetworkData& networkData = player.getNetworkData();
		if (networkData.network == nullptr
			|| networkData.network->getNetworkType() != ENetworkType_RakNetLegacy)
		{
			return "RPC73 fixture requires the legacy RakNet transport";
		}
		return nullptr;
	}

	template <std::size_t PayloadSize>
	bool sendPayload(
		IPlayer& player,
		const char* phase,
		int style,
		const char* text,
		const std::array<uint8_t, PayloadSize>& fixedPayload,
		const char* payloadHex)
	{
		// OPENMP_REF:
		// SDK/include/network.hpp defines Span::size as a count of bits here.
		// A local copy keeps the non-owning transport buffer mutable and alive
		// for the complete synchronous sendRPC call.
		std::array<uint8_t, PayloadSize> payload = fixedPayload;
		const bool sent = player.sendRPC(
			kRpcDisplayGameText,
			Span<uint8_t>(payload.data(), payload.size() * 8u),
			OrderingChannel_SyncRPC,
			false);

		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc73_gametext_fixture] phase=%s player=%d rpc=73 "
				"style=%d time_ms=%d text_len=%u payload_bits=%u "
				"payload=%s text=%s dispatchEvents=0 channel=%d sent=%d",
				phase,
				player.getID(),
				style,
				static_cast<int>(kDisplayTimeMs),
				static_cast<unsigned>(PayloadSize - 12u),
				static_cast<unsigned>(PayloadSize * 8u),
				payloadHex,
				text,
				static_cast<int>(OrderingChannel_SyncRPC),
				sent ? 1 : 0);
		}
		return sent;
	}

	void onReplacementTimer(
		ITimer& timer,
		int playerID,
		uint32_t generation)
	{
		if (!validPlayerID(playerID))
		{
			return;
		}
		const std::size_t index = static_cast<std::size_t>(playerID);
		if (pending_[index] != &timer || generations_[index] != generation)
		{
			if (core_ != nullptr)
			{
				core_->printLn(
					"[rpc73_gametext_fixture] stale_timer player=%d "
					"generation=%u current_generation=%u",
					playerID,
					static_cast<unsigned>(generation),
					static_cast<unsigned>(generations_[index]));
			}
			return;
		}
		pending_[index] = nullptr;

		IPlayer* player = core_ == nullptr
			? nullptr
			: core_->getPlayers().get(playerID);
		if (player == nullptr)
		{
			logTimerAbort(playerID, generation, "player_missing");
			return;
		}
		const char* failure = eligibilityFailure(*player);
		if (failure != nullptr)
		{
			logTimerAbort(playerID, generation, failure);
			return;
		}

		const bool sent = sendPayload(
			*player,
			"replacement",
			3,
			kReplacementText,
			kReplacementPayload,
			kReplacementPayloadHex);
		if (sent)
		{
			player->sendClientMessage(
				Colour::White(),
				"RPC73 fixed style 3 replacement sent.");
		}
		else
		{
			player->sendClientMessage(
				Colour::White(),
				"RPC73 replacement transport failed; inspect server log.");
		}
	}

	void logTimerAbort(
		int playerID,
		uint32_t generation,
		const char* reason)
	{
		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc73_gametext_fixture] timer_abort player=%d "
				"generation=%u reason=%s",
				playerID,
				static_cast<unsigned>(generation),
				reason);
		}
	}

	uint32_t bumpGeneration(std::size_t index)
	{
		++generations_[index];
		if (generations_[index] == 0u)
		{
			++generations_[index];
		}
		return generations_[index];
	}

	void cancelPending(int playerID)
	{
		const std::size_t index = static_cast<std::size_t>(playerID);
		ITimer* timer = pending_[index];
		if (timer != nullptr)
		{
			if (timers_ != nullptr)
			{
				timer->kill();
			}
			pending_[index] = nullptr;
		}
		(void)bumpGeneration(index);
	}

	void cancelAll()
	{
		for (int playerID = 0; playerID < PLAYER_POOL_SIZE; ++playerID)
		{
			cancelPending(playerID);
		}
	}

	void reject(IPlayer& player, const char* reason)
	{
		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc73_gametext_fixture] reject player=%d reason=%s",
				player.getID(),
				reason);
		}
		player.sendClientMessage(Colour::White(), reason);
	}

	void detach()
	{
		if (core_ != nullptr && attached_)
		{
			core_->getPlayers().getPlayerTextDispatcher().removeEventHandler(this);
			core_->getPlayers().getPlayerConnectDispatcher().removeEventHandler(this);
		}
		attached_ = false;
		core_ = nullptr;
	}

	ICore* core_ = nullptr;
	ITimersComponent* timers_ = nullptr;
	std::array<bool, PLAYER_POOL_SIZE> fired_ {};
	std::array<ITimer*, PLAYER_POOL_SIZE> pending_ {};
	std::array<uint32_t, PLAYER_POOL_SIZE> generations_ {};
	bool attached_ = false;
};

void ReplacementTimer::timeout(ITimer& timer)
{
	owner_.onReplacementTimer(timer, playerID_, generation_);
}
} // namespace

COMPONENT_ENTRY_POINT()
{
	return new (std::nothrow) Rpc73GameTextFixture();
}
