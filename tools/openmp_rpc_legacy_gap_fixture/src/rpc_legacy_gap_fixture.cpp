#include <sdk.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <new>

namespace
{
constexpr StringView kCommand = "/rpclegacyraw";
constexpr StringView kDrunkOnCommand = "/rpclegacydrunkon";
constexpr StringView kDrunkOffCommand = "/rpclegacydrunkoff";

struct FixedCase
{
	const char* name;
	int rpc;
	std::array<uint8_t, 4> payload;
	std::size_t payloadBits;
};

// STATIC_037:
// SA-MP 0.3.7-R5, SHA256
// b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
// The RPC IDs, exact payloads and bit counts are closed laboratory vectors
// recovered from the registration inventory and their individual handlers.
// No command or player input can influence them.
constexpr std::array<FixedCase, 14> kCases { {
	{ "world_1", 48, { 0x01, 0x00, 0x00, 0x00 }, 32 },
	{ "world_0", 48, { 0x00, 0x00, 0x00, 0x00 }, 32 },
	{ "drunk_visual_2500", 92, { 0xC4, 0x09, 0x00, 0x00 }, 32 },
	{ "drunk_visual_0", 92, { 0x00, 0x00, 0x00, 0x00 }, 32 },
	{ "vehicle0_tire_1", 98, { 0x00, 0x00, 0x01, 0x00 }, 24 },
	{ "vehicle0_tire_0", 98, { 0x00, 0x00, 0x00, 0x00 }, 24 },
	{ "widescreen_1", 111, { 0x01, 0x00, 0x00, 0x00 }, 8 },
	{ "widescreen_0", 111, { 0x00, 0x00, 0x00, 0x00 }, 8 },
	{ "registered_noop", 125, { 0x00, 0x00, 0x00, 0x00 }, 0 },
	{ "drunk_handling_2500", 150, { 0xC4, 0x09, 0x00, 0x00 }, 32 },
	{ "drunk_handling_0", 150, { 0x00, 0x00, 0x00, 0x00 }, 32 },
	{ "remote_vehicle_collisions_disabled", 167, { 0x80, 0x00, 0x00, 0x00 }, 1 },
	{ "remote_vehicle_collisions_enabled", 167, { 0x00, 0x00, 0x00, 0x00 }, 1 },
	{ "actor0_invulnerable", 169, { 0x00, 0x00, 0x00, 0x00 }, 16 },
} };

constexpr bool casesAreBounded()
{
	for (const FixedCase& test : kCases)
	{
		if (test.rpc < 0 || test.rpc > 255 || test.payloadBits > 32)
		{
			return false;
		}
	}
	return true;
}

static_assert(kCases.size() == 14);
static_assert(casesAreBounded());
static_assert(kCases[8].payloadBits == 0);
static_assert(kCases[11].payloadBits == 1);
static_assert(kCases[11].payload[0] == 0x80);

class LegacyGapFixture final
	: public IComponent
	, public PlayerTextEventHandler
	, public PlayerConnectEventHandler
{
public:
	PROVIDE_UID(0x4C45474143594750);

	~LegacyGapFixture() override
	{
		detach();
	}

	StringView componentName() const override
	{
		return "Closed R5 legacy RPC gap fixture";
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
			"[rpc_legacy_gap_fixture] loaded commands=/rpclegacyraw,"
			"/rpclegacydrunkon,/rpclegacydrunkoff cases=14 "
			"dispatchEvents=0 channel=SyncRPC");
	}

	void onInit(IComponentList*) override
	{
	}

	void onFree(IComponent*) override
	{
	}

	void free() override
	{
		delete this;
	}

	void reset() override
	{
		fired_.fill(false);
	}

	void onPlayerDisconnect(IPlayer& player, PeerDisconnectReason) override
	{
		const int id = player.getID();
		if (validPlayer(id))
		{
			fired_[static_cast<std::size_t>(id)] = false;
		}
	}

	bool onPlayerCommandText(IPlayer& player, StringView message) override
	{
		const bool rawBurst = message == kCommand;
		const bool drunkOn = message == kDrunkOnCommand;
		const bool drunkOff = message == kDrunkOffCommand;
		if (!rawBurst && !drunkOn && !drunkOff)
		{
			return false;
		}

		const int playerID = player.getID();
		if (!validPlayer(playerID) || player.isBot()
			|| player.getClientVersion() != ClientVersion::ClientVersion_SAMP_037
			|| player.getState() == PlayerState_None)
		{
			reject(player, "RPC legacy fixture requires an initialized SA-MP 0.3.7 player");
			return true;
		}
		const PeerNetworkData& networkData = player.getNetworkData();
		if (networkData.network == nullptr
			|| networkData.network->getNetworkType() != ENetworkType_RakNetLegacy)
		{
			reject(player, "RPC legacy fixture requires the legacy RakNet transport");
			return true;
		}

		if (drunkOn || drunkOff)
		{
			// STATIC_037:
			// RPC 92 invokes GTA opcode 052C and RPC 150 invokes opcode
			// 03FD.  Split fixed on/off vectors prove that the client bridge
			// observes each non-zero transition instead of only the final
			// snapshot from the all-in-one burst.
			const uint32_t level = drunkOn ? 2500u : 0u;
			std::array<uint8_t, 4> payload {
				static_cast<uint8_t>(level & 0xFFu),
				static_cast<uint8_t>((level >> 8u) & 0xFFu),
				static_cast<uint8_t>((level >> 16u) & 0xFFu),
				static_cast<uint8_t>((level >> 24u) & 0xFFu),
			};
			unsigned sentCount = 0;
			for (const int rpc : { 92, 150 })
			{
				const bool sent = player.sendRPC(
					rpc,
					Span<uint8_t>(payload.data(), 32),
					OrderingChannel_SyncRPC,
					false);
				sentCount += sent ? 1u : 0u;
				if (core_ != nullptr)
				{
					core_->printLn(
						"[rpc_legacy_gap_fixture] drunk_transition rpc=%d "
						"level=%u bits=32 sent=%d",
						rpc, static_cast<unsigned>(level), sent ? 1 : 0);
				}
			}
			char result[96] {};
			std::snprintf(
				result, sizeof(result),
				"RPC legacy drunk transition level=%u sent %u/2.",
				static_cast<unsigned>(level), sentCount);
			player.sendClientMessage(Colour::White(), result);
			return true;
		}

		const std::size_t index = static_cast<std::size_t>(playerID);
		if (fired_[index])
		{
			reject(player, "RPC legacy fixture is one-shot per connection");
			return true;
		}
		fired_[index] = true;

		unsigned sentCount = 0;
		unsigned caseIndex = 0;
		for (const FixedCase& test : kCases)
		{
			std::array<uint8_t, 4> payload = test.payload;
			const bool sent = player.sendRPC(
				test.rpc,
				Span<uint8_t>(payload.data(), test.payloadBits),
				OrderingChannel_SyncRPC,
				false);
			sentCount += sent ? 1u : 0u;
			if (core_ != nullptr)
			{
				core_->printLn(
					"[rpc_legacy_gap_fixture] case=%u name=%s rpc=%d bits=%u "
					"payload=%02x%02x%02x%02x sent=%d",
					caseIndex, test.name, test.rpc,
					static_cast<unsigned>(test.payloadBits),
					static_cast<unsigned>(test.payload[0]),
					static_cast<unsigned>(test.payload[1]),
					static_cast<unsigned>(test.payload[2]),
					static_cast<unsigned>(test.payload[3]),
					sent ? 1 : 0);
			}
			++caseIndex;
		}

		char result[96] {};
		std::snprintf(
			result, sizeof(result),
			"RPC legacy fixture sent %u/%u fixed vectors; reconnect to rerun.",
			sentCount, static_cast<unsigned>(kCases.size()));
		player.sendClientMessage(Colour::White(), result);
		return true;
	}

private:
	static bool validPlayer(int id)
	{
		return id >= 0 && id < PLAYER_POOL_SIZE;
	}

	void reject(IPlayer& player, const char* reason)
	{
		if (core_ != nullptr)
		{
			core_->printLn(
				"[rpc_legacy_gap_fixture] reject player=%d reason=%s",
				player.getID(), reason);
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
	std::array<bool, PLAYER_POOL_SIZE> fired_ {};
	bool attached_ = false;
};
} // namespace

COMPONENT_ENTRY_POINT()
{
	return new (std::nothrow) LegacyGapFixture();
}
