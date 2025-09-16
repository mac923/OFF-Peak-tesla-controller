# What is Fleet API?

Fleet API is a data and command service providing access to Tesla vehicles, energy, and other types of devices. Partners can interact with their own devices, or devices for which they have been granted access by a customer.  
Follow the onboarding process below to register and get an API key to interact with Tesla's API endpoints. Applications can request vehicle owners for permission to view account information, get vehicle status or even issue remote commands. Vehicle owners maintain control over which application they grant access to, and can change these settings at any time.

## Step 1: Create a Tesla Account

Create a Tesla account and ensure it has a verified email and multi-factor authentication enabled.

[Create Account](https://developer.tesla.com/teslaaccount)

## Step 2: Create an Application

Click the button below to request app access. Provide legal business details, application name, description, and purpose of usage.  
While requesting access, select the scopes used by the application. Reference the [authentication overview page](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes) for a list of available scopes.  
Note: account creation requests can be automatically rejected if the application name already exists.

[Create Application and Access Dashboard](https://developer.tesla.com/dashboard)

## Step 3: Generate a Public/Private Key Pair

A public key must be hosted on the application's domain before making calls to Fleet API.  
The key is used to validate ownership of the domain and provide additional security when using [Vehicle Commands](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) and [Fleet Telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry).  
To create a private key, run:  
openssl ecparam \-name prime256v1 \-genkey \-noout \-out private-key.pem

Then, generate the associated public key.  
openssl ec \-in private-key.pem \-pubout \-out public-key.pem

This public key should be available at:  
https://developer-domain.com/.well-known/appspecific/com.tesla.3p.public-key.pem

Note: private-key.pem needs to be kept secret and should not be hosted on a domain.

## Step 4: Call the Register Endpoint

Next, generate a [partner authentication token](https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens) and use it to call the [register endpoint](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints#register) to complete registration with Fleet API.

## Next Steps

Now that the register endpoint has been called, Fleet API is configured and ready to receive requests.  
Next steps to take:

* Selecting the proper authentication token type and generating tokens. [Authentication overview](https://developer.tesla.com/docs/fleet-api/authentication/overview).  
* [Pairing a public key to a vehicle](https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide#adding-to-a-vehicle). This is required to send [Vehicle Commands](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) and setup [Fleet Telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry).  
* Configuring [Fleet Telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry) which streams data directly to a server.

# 

# Developer

# [Skip to main content](https://developer.tesla.com/docs/fleet-api/authentication/overview#main-content)

* [Documentation](https://developer.tesla.com/docs/fleet-api/getting-started/what-is-fleet-api)  
* [Charging](https://developer.tesla.com/docs/charging/roaming)  
* 

# Authentication

API endpoints require an authentication token. It must be included as a header:  
Authorization: Bearer \<token\>

## Token Types

There are four types of tokens, each used with a different purpose. Identifying the proper token type is important. Otherwise, the API will return unexpected responses.  
Choose a token type based on use case.

1. Developers building closed-source software on top of Fleet API that will access user's accounts: [Third-party token](https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens).  
2. Businesses registered with Tesla for Business looking to interact with their Tesla products: [Partner token](https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens).  
   * Businesses can self-onboard to Tesla for Business by visiting the [self-onboarding page](https://accounts.tesla.com/business/get-started).  
3. Hobbyists looking to interact with their own Tesla products: [Third-party token](https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens).  
4. Applications authenticating on behalf of a business: [Third-party for Business token](https://developer.tesla.com/docs/fleet-api/authentication/third-party-business-tokens).  
5. All calls to [Partner Endpoints](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints): [Partner token](https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens).

## Scopes

Scopes are used to limit API access to only the data an application needs.

| Name | Scope | Description |
| ----- | ----- | ----- |
| Sign in with Tesla | openid | Allow Tesla customers to sign in to the application with their Tesla credentials. |
| Refresh Tokens | offline\_access | Allow getting a refresh token without needing user to log in again. |
| Profile Information | user\_data | Contact information, home address, profile picture, and referral information. |
| Vehicle Information | vehicle\_device\_data | Allow access to your vehicle’s live data, service history, service scheduling data, service communications, eligible upgrades, nearby Superchargers and ownership details. Note: This permission grants vehicle location data access. In the first quarter of 2025, only the vehicle location permission will control location data access. |
| Vehicle Location | vehicle\_location | Allow access to vehicle location information, including data such as precise location, and coarse location for approximate location services. |
| Vehicle Commands | vehicle\_cmds | Commands like add/remove driver, access Live Camera, unlock, wake up, remote start, and schedule software updates. |
| Vehicle Charging Management | vehicle\_charging\_cmds | Vehicle charging history, billed amount, charging location, commands to schedule, and start/stop charging. |
| Energy Product Information | energy\_device\_data | Energy live status, site info, backup history, energy history, and charge history. |
| Energy Product Settings | energy\_cmds | Update settings like backup reserve percent, operation mode, and storm mode. |

## Useful Links

The OAuth server's metadata file can be found at: [https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/thirdparty/.well-known/openid-configuration](https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/thirdparty/.well-known/openid-configuration).  
A Postman collection with these requests can be found [here](https://www.postman.com/crimson-space-512892/workspace/fleet-api/collection/33220881-5d29d2ee-0aad-494c-b469-c2d510125f5b).

# Developer's Guide to Virtual Keys

A virtual key is a public/private key pair which enables authorization when interacting with a vehicle. The public key must be added to the vehicle by a trusted user and the private key is kept securely on the application's server. Before executing a command or accepting a Fleet Telemetry configuration, the vehicle ensures the payload is signed by a private key whose public key is present on the vehicle.

## Design Explanation

The virtual key provides a crucial layer of protection for users. Adding the key to a vehicle requires a trusted user-in-the-loop, preventing even Tesla's backend from accessing these capabilities. This ensures only authorized parties are able to execute commands or access device data through Fleet Telemetry. If at any time the user wishes to revoke access, they can remove the virtual key from the Locks screen.

## Setup Steps

### Creating a Key Pair

To create a private key, run:  
openssl ecparam \-name prime256v1 \-genkey \-noout \-out private-key.pem

Then, generate the associated public key.  
openssl ec \-in private-key.pem \-pubout \-out public-key.pem

Note: the vehicle only supports prime256v1 keys.

### Hosting the Public Key

This public key must remain available at:  
https://developer-domain.com/.well-known/appspecific/com.tesla.3p.public-key.pem

Note: private-key.pem needs to be kept secret and should never be hosted on a domain.  
After the public key is publicly accessible, call the [Partner Account register](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints#register) endpoint to enroll this key with Tesla.

### Adding to a Vehicle

Applications will have their virtual key added automatically to vehicles purchased through the [B2B program](https://accounts.tesla.com/business/get-started). Note: these vehicles must have fewer than 20 paired keys and must not require the vehicle command protocol; both of these states are present on the [fleet\_status](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-status) endpoint. Vehicles purchased outside the B2B program do not allow Tesla to remotely add keys. For these cases, the virtual key must be added by a user with vehicle access.  
To request virtual key pairing via the Tesla mobile app:

1. Ensure the user has [authorized the application](https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens#step-1-user-authorization) and granted the vehicle\_device\_data, vehicle\_cmds, or vehicle\_location scopes.  
2. Direct the user to the key pairing deep link with the Application's domain:

https://tesla.com/\_ak/\*developer-domain.com\*

Users with multiple vehicles can select the vehicle before opening the key paring link, or an optional vin parameter can be added:  
https://tesla.com/\_ak/\*developer-domain.com\*?vin=VIN123

### Removing Key

To remove a key, the user must navigate to the Locks screen in the vehicle and delete the key. Access can also be revoked remotely by revoking the third-party application's access.

## Terminology

* Virtual key: A virtual key is a public/private key pair used by a developer application to securely communicate with a vehicle.  
* Public key: A cryptographic key used by the vehicle to validate a payload comes from a trusted source.  
* Private key: A cryptographic key used by the Vehicle Command Proxy to sign payloads sent to the vehicle. The private key must be kept secret to prevent unauthorized access to the vehicle.  
* Signed commands: A signed command is a command (such as unlock door) which is signed by the application's private key. The easiest method to sign commands is through the Vehicle Command Proxy.

# Vehicle Commands

Vehicle commands allow direct interaction with a vehicle. To accept commands, a vehicle must have an application's virtual key installed. Full details about virtual keys are available in the virtual keys [developer guide](https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide). The Vehicle Command Proxy exposes a REST API for sending commands.  
The [Vehicle Command Proxy](https://github.com/teslamotors/vehicle-command) exposes endpoints identical to the ones described below. When it receives a request, it signs the command with a virtual key before passing the request to Fleet API. If a command is not signed, the vehicle will reject the request and perform no action. This ensures unauthorized parties are not able to send commands.  
Note: The Vehicle Commands Proxy is not required for most business vehicles and Pre-2021 S and X vehicles.

## Endpoints

### actuate\_trunk

POST /api/1/vehicles/{vehicle\_tag}/command/actuate\_trunk  
Controls the front (which\_trunk: "front") or rear (which\_trunk: "rear") trunk.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### which\_trunk

body

required

The trunk to actuate. front or rear.

### add\_charge\_schedule

POST /api/1/vehicles/{vehicle\_tag}/command/add\_charge\_schedule  
Add a schedule for vehicle charging. To view existing schedules, call the [vehicle\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#vehicle-data) endpoint and request charge\_schedule\_data.  
Related: [remove charge schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#remove-charge-schedule)

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### days\_of\_week

body

required

A comma separated list of days this schedule should be enabled. Example: "Thursday,Saturday". Also supports "All" and "Weekdays".

###### enabled

body

required

If this schedule should be considered for execution.

###### end\_enabled

body

required

If the vehicle should stop charging after the given end\_time.

###### lat

body

required

The approximate latitude the vehicle must be at to use this schedule.

###### lon

body

required

The approximate longitude the vehicle must be at to use this schedule.

###### start\_enabled

body

required

If the vehicle should begin charging at the given start\_time.

###### end\_time

body

The number of minutes into the day this schedule ends. 1:05 AM is represented as 65. Omit if end\_enabled set to false.

###### id

body

The ID of an existing schedule to modify. Omit if creating a new schedule.

###### one\_time

body

If this is a one-time schedule.

###### start\_time

body

The number of minutes into the day this schedule begins. 1:05 AM is represented as 65. Omit if start\_enabled set to false.

### add\_precondition\_schedule

POST /api/1/vehicles/{vehicle\_tag}/command/add\_precondition\_schedule  
Add or modify a preconditioning schedule. To view existing schedules, call the [vehicle\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#vehicle-data) endpoint and request preconditioning\_schedule\_data.  
Related: [remove precondition schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#remove-precondition-schedule)

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### days\_of\_week

body

required

A comma separated list of days this schedule should be enabled. Example: "Thursday,Saturday". Also supports "All" and "Weekdays".

###### enabled

body

required

If this schedule should be considered for execution.

###### lat

body

required

The approximate latitude the vehicle must be at to use this schedule.

###### lon

body

required

The approximate longitude the vehicle must be at to use this schedule.

###### precondition\_time

body

required

The number of minutes into the day the vehicle should complete preconditioning. 1:05 AM is represented as 65.

###### id

body

The ID of an existing schedule to modify. Omit if creating a new schedule.

###### one\_time

body

If this is a one-time schedule.

### adjust\_volume

POST /api/1/vehicles/{vehicle\_tag}/command/adjust\_volume  
Adjusts vehicle media playback volume. This command requires the user to be present and mobile access to be enabled.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### volume

body

required

A floating point number from 0.0 to 11.0.

### auto\_conditioning\_start

POST /api/1/vehicles/{vehicle\_tag}/command/auto\_conditioning\_start  
Starts climate preconditioning.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### auto\_conditioning\_stop

POST /api/1/vehicles/{vehicle\_tag}/command/auto\_conditioning\_stop  
Stops climate preconditioning.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### cancel\_software\_update

POST /api/1/vehicles/{vehicle\_tag}/command/cancel\_software\_update  
Cancels the countdown to install the vehicle software update. This operation will no longer work after the vehicle begins the software installation.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_max\_range

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_max\_range  
Charges in max range mode \-- we recommend limiting the use of this mode to long trips.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_port\_door\_close

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_port\_door\_close  
Closes the charge port door. This command will return errors depending on the vehicle state.

* cable connected \- a charge cable is plugged into the vehicle.  
* non-motorized charge port \- the vehicle is not equipped with a motorized charge port. This applies to older Model S and Model X vehicles.  
* already closed \- the charge port door is already closed.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_port\_door\_open

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_port\_door\_open  
Opens the charge port door. This command will return errors depending on the vehicle state.

* car\_wash \- the vehicle is in car wash mode.  
* not allowed \- the vehicle's drive rail in engaged or the vehicle is not in park.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_standard

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_standard  
Charges in Standard mode. This command may return already\_started if the existing charge limit request is already less than or equal to the standard/default charge limit.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_start

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_start  
Starts charging the vehicle. This command may return errors if the vehicle is unable to begin charging.

* complete \- the vehicle has already completed charging.  
* is\_charging \- the vehicle is already charging.  
* disconnected \- the vehicle is not connected to a charger.  
* no\_power \- the connected charger is unable to provide power.  
* requested \- the vehicle has already received a start charge request.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### charge\_stop

POST /api/1/vehicles/{vehicle\_tag}/command/charge\_stop  
Stops charging the vehicle. This command will return not\_charging if the vehicle is not currently charging.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### clear\_pin\_to\_drive\_admin

POST /api/1/vehicles/{vehicle\_tag}/command/clear\_pin\_to\_drive\_admin  
Deactivates PIN to Drive and resets the associated PIN for vehicles running firmware versions 2023.44+. This command is only accessible to fleet managers or owners.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### door\_lock

POST /api/1/vehicles/{vehicle\_tag}/command/door\_lock  
Locks the vehicle.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### door\_unlock

POST /api/1/vehicles/{vehicle\_tag}/command/door\_unlock  
Unlocks the vehicle.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### erase\_user\_data

POST /api/1/vehicles/{vehicle\_tag}/command/erase\_user\_data  
Erases user's data from the user interface. Requires the vehicle to be parked and in [Guest Mode](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#guest_mode).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### flash\_lights

POST /api/1/vehicles/{vehicle\_tag}/command/flash\_lights  
Briefly flashes the vehicle headlights. Requires the vehicle to be in park.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### guest\_mode

POST /api/1/vehicles/{vehicle\_tag}/command/guest\_mode

* Restricts certain vehicle UI functionality from guest users:  
  * PIN to Drive  
  * Speed Limit Mode  
  * Glovebox PIN  
  * Add/Remove keys  
  * Change vehicle name  
* Allows [erase\_user\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#erase_user_data) on the vehicle.  
* Allows a user to set up Tesla mobile app access with the vehicle key card:  
  * If a user unlocks a vehicle or authenticates it for drive with a key card, they will receive a prompt to set up their phone as key by scanning a QR code on the vehicle touchscreen.  
    * The QR code is single-use and expires after 10 minutes.  
    * Requires vehicle firmware version 2024.14+.  
  * Any account that scans the QR code will gain Tesla app access to the vehicle, and download that account's Tesla profile to the vehicle.  
    * Tesla app access allows a user to view live vehicle location, issue remote commands, and set up their phone as key within Bluetooth proximity of the vehicle.  
    * Guest access will not have certain driver access features such as Service and Roadside.  
  * Guest access is automatically removed when:  
    * A key card is used to drive the vehicle.  
    * A new QR code is scanned (only one guest is allowed at a time).  
    * Guest Mode is disabled.  
  * In addition, one can use the [drivers remove](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#drivers-remove) endpoint to remotely revoke guest access.  
  * If a user does not have the app installed, they will see this webpage ([https://www.tesla.com/\_gs/test](https://www.tesla.com/_gs/test)) to guide them through the process.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### enable

body

required

### honk\_horn

POST /api/1/vehicles/{vehicle\_tag}/command/honk\_horn  
Honks the vehicle horn. Requires the vehicle to be in park.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_next\_fav

POST /api/1/vehicles/{vehicle\_tag}/command/media\_next\_fav  
Advances media player to next favorite track.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_next\_track

POST /api/1/vehicles/{vehicle\_tag}/command/media\_next\_track  
Advances media player to next track.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_prev\_fav

POST /api/1/vehicles/{vehicle\_tag}/command/media\_prev\_fav  
Advances media player to previous favorite track.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_prev\_track

POST /api/1/vehicles/{vehicle\_tag}/command/media\_prev\_track  
Advances media player to previous track.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_toggle\_playback

POST /api/1/vehicles/{vehicle\_tag}/command/media\_toggle\_playback  
Toggles current play/pause state.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### media\_volume\_down

POST /api/1/vehicles/{vehicle\_tag}/command/media\_volume\_down  
Turns the volume down by one.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### navigation\_gps\_request

POST /api/1/vehicles/{vehicle\_tag}/command/navigation\_gps\_request  
Start navigation to given coordinates. Order can be used to specify order of multiple stops.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### lat

body

required

###### lon

body

required

###### order

body

required

### navigation\_request

POST /api/1/vehicles/{vehicle\_tag}/command/navigation\_request  
Sends a location to the in-vehicle navigation system.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### locale

body

required

###### timestamp\_ms

body

required

###### type

body

required

###### value

body

required

An object representing a location share request. Common phone platform map application share content formats supported.

### navigation\_sc\_request

POST /api/1/vehicles/{vehicle\_tag}/command/navigation\_sc\_request  
Start navigation to a supercharger.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### id

body

required

###### order

body

required

### navigation\_waypoints\_request

POST /api/1/vehicles/{vehicle\_tag}/command/navigation\_waypoints\_request  
Sends a list of waypoints to the vehicle's navigation system.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### waypoints

body

required

A comma separated string of refId:\<Google Maps place ID\>. More information about place IDs is available [here](https://developers.google.com/maps/documentation/places/web-service/place-id).

### remote\_auto\_seat\_climate\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_auto\_seat\_climate\_request  
Sets automatic seat heating and cooling. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### auto\_climate\_on

body

required

###### auto\_seat\_position

body

required

### remote\_auto\_steering\_wheel\_heat\_climate\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_auto\_steering\_wheel\_heat\_climate\_request  
Sets automatic steering wheel heating on/off. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### on

body

required

### remote\_boombox

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_boombox  
Plays a sound through the vehicle external speaker.  
Sound IDs:

* 0: random fart  
* 2000: locate ping

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### sound

body

required

### remote\_seat\_cooler\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_seat\_cooler\_request  
Sets seat cooling. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### seat\_cooler\_level

body

required

The cooling level.

* 0: off  
* 1: low  
* 2: medium  
* 3: high

###### seat\_position

body

required

The seat to set cooling for.

* 1: front left  
* 2: front right

### remote\_seat\_heater\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_seat\_heater\_request  
Sets seat heating. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### level

body

required

The heating level.

* 0: off  
* 1: low  
* 2: medium  
* 3: high

###### seat\_position

body

required

The seat to set heat level for.

* 0: front left  
* 1: front right  
* 2: rear left  
* 3: rear left back  
* 4: rear center  
* 5: rear right  
* 6: rear right back  
* 7: third row left  
* 8: third row right

### remote\_start\_drive

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_start\_drive  
Starts the vehicle remotely. Requires keyless driving to be enabled.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### remote\_steering\_wheel\_heat\_level\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_steering\_wheel\_heat\_level\_request  
Sets steering wheel heat level. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### level

body

required

The heating level.

* 0: off  
* 1: low  
* 3: high

### remote\_steering\_wheel\_heater\_request

POST /api/1/vehicles/{vehicle\_tag}/command/remote\_steering\_wheel\_heater\_request  
Sets steering wheel heating on/off. For vehicles that do not support auto steering wheel heat. Requires [preconditioning](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#auto-conditioning-start) or climate keeper to be on.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### on

body

required

### remove\_charge\_schedule

POST /api/1/vehicles/{vehicle\_tag}/command/remove\_charge\_schedule  
Remove a charge schedule by ID. To view existing schedules, call the [vehicle\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#vehicle-data) endpoint and request charge\_schedule\_data.  
Related: [add charge schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#add-charge-schedule)

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### id

body

required

The ID of the schedule to delete.

### remove\_precondition\_schedule

POST /api/1/vehicles/{vehicle\_tag}/command/remove\_precondition\_schedule  
Remove a precondition schedule by ID. To view existing schedules, call the [vehicle\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#vehicle-data) endpoint and request preconditioning\_schedule\_data.  
Related: [add precondition schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#add-precondition-schedule)

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### id

body

required

The ID of the schedule to delete.

### reset\_pin\_to\_drive\_pin

POST /api/1/vehicles/{vehicle\_tag}/command/reset\_pin\_to\_drive\_pin  
Removes PIN to Drive. Requires the car to be in Pin to Drive mode and not in Valet mode. Note that this only works if PIN to Drive is not active. This command is only accessible to fleet managers or owners. This command also requires the Tesla Vehicle Command Protocol \- for more information, refer to the documentation [here](https://developer.tesla.com/docs/fleet-api/announcements#2023-10-09-rest-api-vehicle-commands-endpoint-deprecation-warning).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### reset\_valet\_pin

POST /api/1/vehicles/{vehicle\_tag}/command/reset\_valet\_pin  
Removes PIN for Valet Mode. To use this command, valet mode must be disabled. See [set\_valet\_mode](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#set-valet-mode).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### schedule\_software\_update

POST /api/1/vehicles/{vehicle\_tag}/command/schedule\_software\_update  
Schedules a vehicle software update (over the air "OTA") to be installed in the future.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### offset\_sec

body

required

### set\_bioweapon\_mode

POST /api/1/vehicles/{vehicle\_tag}/command/set\_bioweapon\_mode  
Turns Bioweapon Defense Mode on and off.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### manual\_override

body

required

###### on

body

required

### set\_cabin\_overheat\_protection

POST /api/1/vehicles/{vehicle\_tag}/command/set\_cabin\_overheat\_protection  
Sets the vehicle overheat protection.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### fan\_only

body

required

###### on

body

required

### set\_charge\_limit

POST /api/1/vehicles/{vehicle\_tag}/command/set\_charge\_limit  
Sets the vehicle charge limit. This command will return already\_set if the requested percent is the same as the existing charge limit.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### percent

body

required

Integer representing the battery % at which charging will stop. Minimum 50, Maximum 100\. Note: invalid percent will return success responses.

### set\_charging\_amps

POST /api/1/vehicles/{vehicle\_tag}/command/set\_charging\_amps  
Sets the vehicle charging amps.

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### charging\_amps

body

required

### set\_climate\_keeper\_mode

POST /api/1/vehicles/{vehicle\_tag}/command/set\_climate\_keeper\_mode  
Enables climate keeper mode. Accepted values are: 0,1,2,3. Mapping to respectively Off, Keep Mode, Dog Mode, Camp Mode.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### climate\_keeper\_mode

body

required

### set\_cop\_temp

POST /api/1/vehicles/{vehicle\_tag}/command/set\_cop\_temp  
Adjusts the Cabin Overheat Protection temperature (COP). This command will not activate COP. The precise target temperature depends on if the user has selected C or F. Accepted values are: 0,1,2. Mapping to respectively Low (90F/30C), Medium (95F/35C), High (100F/40C).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### cop\_temp

body

required

### set\_pin\_to\_drive

POST /api/1/vehicles/{vehicle\_tag}/command/set\_pin\_to\_drive  
Sets a four-digit passcode for PIN to Drive. This PIN must then be entered before the vehicle can be driven. Once a PIN is set, the vehicle remembers its value even when PIN to Drive is disabled and it will discard any new PIN provided using this method. To change an existing PIN, first call reset\_pin\_to\_drive\_pin. This command is only accessible to fleet managers or owners. This command also requires the Tesla Vehicle Command Protocol \- for more information, refer to the documentation [here](https://developer.tesla.com/docs/fleet-api/announcements#2023-10-09-rest-api-vehicle-commands-endpoint-deprecation-warning).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### on

body

required

###### password

body

required

### set\_preconditioning\_max

POST /api/1/vehicles/{vehicle\_tag}/command/set\_preconditioning\_max  
Sets an override for preconditioning — it should default to empty if no override is used.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### manual\_override

body

required

###### on

body

required

### set\_scheduled\_charging

POST /api/1/vehicles/{vehicle\_tag}/command/set\_scheduled\_charging  
This endpoint is not recommended beginning with firmware version 2024.26. The [add charge schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#add-charge-schedule) command should be used instead.  
Sets a time at which charging should be completed. The time parameter is minutes after midnight (e.g: time=120 schedules charging for 2:00am vehicle local time).

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### enable

body

required

###### time

body

required

### set\_scheduled\_departure

POST /api/1/vehicles/{vehicle\_tag}/command/set\_scheduled\_departure  
This endpoint is not recommended beginning with firmware version 2024.26. The [add precondition schedule](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands#add-precondition-schedule) command should be used instead.  
Sets a time at which departure should be completed. The departure\_time and end\_off\_peak\_time parameters are minutes after midnight (e.g: departure\_time=120 schedules departure for 2:00am vehicle local time).

DetailsRequestResponse

#### Scopes

vehicle\_cmdsvehicle\_charging\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### departure\_time

body

required

###### enable

body

required

###### end\_off\_peak\_time

body

###### off\_peak\_charging\_enabled

body

###### off\_peak\_charging\_weekdays\_only

body

###### preconditioning\_enabled

body

### set\_sentry\_mode

POST /api/1/vehicles/{vehicle\_tag}/command/set\_sentry\_mode  
Enables and disables Sentry Mode. Sentry Mode allows customers to watch the vehicle cameras live from the mobile app, as well as record sentry events.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### on

body

required

### set\_temps

POST /api/1/vehicles/{vehicle\_tag}/command/set\_temps  
Sets the driver and/or passenger-side cabin temperature (and other zones if sync is enabled).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### driver\_temp

body

required

###### passenger\_temp

body

required

### set\_valet\_mode

POST /api/1/vehicles/{vehicle\_tag}/command/set\_valet\_mode  
Turns on Valet Mode and sets a four-digit passcode that must then be entered to disable Valet Mode.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### on

body

required

###### password

body

required

### set\_vehicle\_name

POST /api/1/vehicles/{vehicle\_tag}/command/set\_vehicle\_name  
Changes the name of a vehicle. Not supported in guest mode. This command also requires the Tesla Vehicle Command Protocol \- for more information, refer to the documentation [here](https://developer.tesla.com/docs/fleet-api/announcements#2023-10-09-rest-api-vehicle-commands-endpoint-deprecation-warning).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### vehicle\_name

body

required

### speed\_limit\_activate

POST /api/1/vehicles/{vehicle\_tag}/command/speed\_limit\_activate  
Activates Speed Limit Mode with a four-digit PIN.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### pin

body

required

### speed\_limit\_clear\_pin

POST /api/1/vehicles/{vehicle\_tag}/command/speed\_limit\_clear\_pin  
Deactivates Speed Limit Mode and resets the associated PIN.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### pin

body

required

### speed\_limit\_clear\_pin\_admin

POST /api/1/vehicles/{vehicle\_tag}/command/speed\_limit\_clear\_pin\_admin  
Deactivates Speed Limit Mode and resets the associated PIN for vehicles running firmware versions 2023.38+. This command is only accessible to fleet managers or owners.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

### speed\_limit\_deactivate

POST /api/1/vehicles/{vehicle\_tag}/command/speed\_limit\_deactivate  
Deactivates Speed Limit Mode.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### pin

body

required

### speed\_limit\_set\_limit

POST /api/1/vehicles/{vehicle\_tag}/command/speed\_limit\_set\_limit  
Sets the maximum speed (in miles per hours) for Speed Limit Mode.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### limit\_mph

body

required

### sun\_roof\_control

POST /api/1/vehicles/{vehicle\_tag}/command/sun\_roof\_control  
Control the sunroof on sunroof-enabled vehicles.  
Supported states: stop, close, and vent.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### state

body

required

### trigger\_homelink

POST /api/1/vehicles/{vehicle\_tag}/command/trigger\_homelink  
Turns on HomeLink (used to open and close garage doors). This command will error with not\_supported if the vehicle is not equipped for HomeLink.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### lat

body

required

###### lon

body

required

###### token

body

required

### upcoming\_calendar\_entries

POST /api/1/vehicles/{vehicle\_tag}/command/upcoming\_calendar\_entries  
Upcoming calendar entries stored on the vehicle.

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### calendar\_data

body

required

### window\_control

POST /api/1/vehicles/{vehicle\_tag}/command/window\_control  
Control the windows of a parked vehicle. Supported commands: vent and close. When closing, specify lat and lon of user to ensure they are within range of vehicle (unless this is an M3 platform vehicle).

DetailsRequestResponse

#### Scopes

vehicle\_cmds

#### Pricing Category

commands

#### Parameters

###### vehicle\_tag

path

required

VIN or id field of a vehicle from /api/1/vehicles endpoint.

###### command

body

required

vent or close.

###### lat

body

###### lon

body

# Fleet Telemetry

Fleet Telemetry is the most efficient and effective way of gathering data from vehicles. It allows vehicles to stream data directly to a server, eliminating the need to poll the [vehicle\_data](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#vehicle-data) endpoint. This prevents unnecessary vehicle wakes and battery drain. Fleet Telemetry is not fully equivalent to the vehicle data endpoint but provides important data in an efficient and economical manner. See [Cost Optimization Case Studies](https://developer.tesla.com/docs/fleet-api/billing-and-limits#cost-optimization-case-studies) for details of the cost savings available by using Fleet Telemetry.

## Server Setup

The Fleet Telemetry server must be running on a server exposed to the public internet. The [GitHub repository](https://github.com/teslamotors/fleet-telemetry) has source code and examples of running the server.

## Vehicle Setup

To configure a vehicle, confirm all pre-requisites are met. Then, send a [configure Fleet Telemetry](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-telemetry-config-create) request through the [vehicle-command](https://github.com/teslamotors/vehicle-command) HTTP proxy. The proxy will sign the configuration using the configured private key and forward the request to Fleet API.

### Prerequisites

For a vehicle to be able to stream data, a few conditions must be met:

* The vehicle must not be a pre-2021 Model S or Model X.  
* Vehicles must be running firmware version 2024.26 or later.  
  * Applications configured with the legacy certificate signing process require 2023.20.6 or later.  
* The [virtual key](https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide) is paired with the vehicle.

#### Pairing a Key

To pair a key to the vehicle, direct the user to:  
https://tesla.com/\_ak/developer-domain.com

This will allow the user to add the key to their vehicle through the Tesla mobile app.  
Troubleshooting:

* If receiving a message stating the user has not granted this third-party app access, ensure the user is logged into the Tesla app with the same email used when authorizing the third-party application.  
* If receiving a message stating the application has not registered with Tesla, ensure the [register endpoint](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints#register) has been called for the region the user is located in. This error will also show if the application's public key is no longer available at the /.well-known/ path on the domain used for application registration. This became a requirement [here](https://developer.tesla.com/docs/fleet-api/announcements#2024-02-02-public-key-must-remain-available-for-pairing-continuity).

### Configuring a Vehicle

Once all pre-requisites are met, use the [Fleet Telemetry configure](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-telemetry-config-create) endpoint to send the desired configuration to the vehicle. Configurations are signed and cannot be edited by Tesla. If a required authorization scope is revoked, making a configuration invalid, the configuration will be removed from the vehicle. A vehicle can be configured to stream data to five third-party applications at a time.  
A full list of fields are available in the open source repository's [vehicle\_data.proto](https://github.com/teslamotors/fleet-telemetry/blob/main/protos/vehicle_data.proto) file. Documentation improvements for available fields are coming soon.  
Note: vehicle\_location scope is required for the following fields: Location, OriginLocation, DestinationLocation, DestinationName, RouteLine, GpsState, GpsHeading

[Configure Vehicle Endpoint](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-telemetry-config-create)

Troubleshooting:

* If a vehicle is configured and awake, but does not begin streaming, check the following:  
  * Ensure the host and CA in your configuration is compatible with your server using [check\_server\_cert.sh](https://github.com/teslamotors/fleet-telemetry/blob/main/tools/check_server_cert.sh).  
  * Ensure the application public key is present on the vehicle using the [fleet\_status](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-status) endpoint. Note: the key state reported in this endpoint may have some lag.

## System Behavior

Fleet Telemetry consists of two event loops:

1. The event collector gathers data in 500 millisecond buckets. Once 500 milliseconds has elapsed, all fields that have emitted values are delivered to the remote server.  
2. Each field's value is only sent to the event collector once two conditions are met: interval\_seconds has elapsed since the field was last emitted and the field's value has changed.

System state transitions:  
Assume the "VehicleSpeed" field is being streamed with interval\_seconds set to 1.

| Time | Event | Action |
| ----- | ----- | ----- |
| 0ms | Process starts. | Begin listening for field changes. All fields are received shortly after startup. In this case, speed is received at 100ms. |
| 100ms | Receive speed of 0mph. | Immediately push to event collector since no value has been seen previously. |
| 500ms | Event collector loop triggers. | Vehicle speed is sent from event collector to remote server. |
| 600ms | Speed changes to 1mph. | The value is not pushed to event collector since interval\_seconds has not elapsed. |
| 1000ms | Event collector loop triggers. | No data is sent to remote server since no updated fields received. |
| 1100ms | Speed changes to 2mph. | The value is not pushed to event collector since interval\_seconds has not elapsed. The previous value of 1mph is discarded. |
| 1300ms | interval\_seconds has elapsed. | Immediately push data to event collector since speed has changed since last publish (from 0mph to 2mph). |
| 1500ms | Event collector loop triggers. | Speed of 2mph is sent. |
| 2000ms | Event collector loop triggers. | No data is sent to remote server since no updated fields received. |
| 2300ms | interval\_seconds has elapsed. | Nothing is pushed to the event collector since speed has not changed. |
| 2400ms | Speed changes to 3mph. | Immediately push to the event collector since interval\_seconds has already elapsed. |
| 2500ms | Event collector loop triggers. | Speed of 3mph is sent. |

Failure handling:

* Loss of connectivity: the vehicle will buffer 5000 messages which is at least 2,500 seconds of data. Once reconnected, all messages will be delivered.  
* Server disconnect: the vehicle will buffer messages, as described above. It will attempt to reconnect in an exponential backoff with a maximum retry delay of 30 seconds.  
* A vehicle's connectivity state can be monitored through Fleet Telemetry [connectivity events](https://github.com/teslamotors/fleet-telemetry?tab=readme-ov-file#detecting-vehicle-connectivity-changes).

## Example Configuration Pricing Analysis

This is a sample configuration which collects data from the most commonly used fields when building applications.  
{  
    "fields": {  
        "VehicleSpeed": { "interval\_seconds": 10 },  
        "Location": { "interval\_seconds": 10 },  
        "Soc": { "interval\_seconds": 60 },  
        "DoorState": { "interval\_seconds": 1 },  
        "Odometer": { "interval\_seconds": 60 },  
        "Locked": { "interval\_seconds": 1 },  
        "EstBatteryRange": { "interval\_seconds": 60 },  
        "ChargeAmps": { "interval\_seconds": 1 },  
        "DetailedChargeState": { "interval\_seconds": 1 },  
        "VehicleName": { "interval\_seconds": 1 },  
        "TpmsPressureFl": { "interval\_seconds": 1 },  
        "TpmsPressureFr": { "interval\_seconds": 1 },  
        "TpmsPressureRl": { "interval\_seconds": 1 },  
        "TpmsPressureRr": { "interval\_seconds": 1 },  
        "TpmsLastSeenPressureTimeFl": { "interval\_seconds": 1 },  
        "TpmsLastSeenPressureTimeFr": { "interval\_seconds": 1 },  
        "TpmsLastSeenPressureTimeRl": { "interval\_seconds": 1 },  
        "TpmsLastSeenPressureTimeRr": { "interval\_seconds": 1 }  
    }  
}  
During regular driving, a small subset of the desired fields are regularly streamed thanks to change based streaming [described above](https://developer.tesla.com/docs/fleet-api/fleet-telemetry#data-collection-interval).

* VehicleSpeed: 6 signals per minute  
* Location: 6 signals per minute  
* Soc: 1 signal per minute  
* Odometer: 1 signal per minute  
* EstBatteryRange: 1 signal per minute  
* Remaining fields: not streamed regularly

This results in approximately 15 signals streamed per minute of driving, yielding a cost of $0.0001/minute or $0.006/hour.  
The other fields are streamed on vehicle startup and infrequently as the value changes. For this estimation, generously assume each field is streamed 3 extra times per hour. This results in 18 \* 3 \= 54 additional signals, yielding a cost of $0.00036/hour.  
For this basic configuration, an hour of driving would cost about $0.00636.

## Changelog

The vehicle publishes a Fleet Telemetry client version on connection and through the [fleet status](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-status) endpoint. This version can be used to identify the capabilities of a given vehicle.

* 1.0.0  
  * Firmware versions this change is introduced in:  
    * 2025.2.6  
    * 2024.45.32.20  
  * New fields have been added, see [Available Data](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) for latest fields.  
  * A new configuration option delivery\_policy has been introduced. When set to latest, the vehicle will resend data which is not acknowledged by the server. When data is resent, all un-acked data will be resent. This requires Fleet Telemetry server version 0.7.1 or later.  
  * Location fields now support minimum\_delta. Changes in distance are measured in meters.  
  * The vehicle now publishes its Fleet Telemetry client version on connection and through the [fleet status](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-status) endpoint.

# Third-Party Tokens

Use the authorization\_code grant flow to generate a token on behalf of a customer. This allows API calls using the [scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes) granted by the customer. Authentication endpoints are not billed.

## Step 1: User Authorization

To initiate the authorization code flow, direct the customer to an /authorize request.  
https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/authorize

### Parameters

| Name | Required | Example | Description |
| ----- | ----- | ----- | ----- |
| response\_type | Yes | code | A string, always use the value "code". |
| client\_id | Yes | abc-123 | Partner application client ID. |
| redirect\_uri | Yes | https://example.com/auth/callback | Partner application callback url, spec: [rfc6749](https://www.rfc-editor.org/rfc/rfc6749#section-3.1.2). |
| scope | Yes | openid offline\_access user\_data vehicle\_device\_data vehicle\_cmds vehicle\_charging\_cmds | Space delimited list of [scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes), include openid and offline\_access to obtain a refresh token. |
| state | Yes | db4af3f87... | Random value used for validation. |
| nonce | No | 7baf90cda... | Random value used for replay prevention. |
| prompt\_missing\_scopes | No | true or false | When true, the user will be prompted to authorize scopes, if they have not already granted all required scopes. |
| require\_requested\_scopes | No | true or false | When true, the user must authorize all requested scopes to proceed. |
| show\_keypair\_step | No | true or false | Inform users there will be a second step in the authorization flow for virtual key pairing. This is meant to be used for cases where an application immediately redirects users to virtual key paring after receiving the authorization code callback. |

### Example Request

https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/authorize?\&client\_id=$CLIENT\_ID\&locale=en-US\&prompt=login\&redirect\_uri=$REDIRECT\_URI\&response\_type=code\&scope=openid%20vehicle\_device\_data%20offline\_access\&state=$STATE

## Step 2: Callback

After the user authorizes their account with Tesla, they will be redirected to the specified redirect\_uri.  
Extract the code URL parameter from this callback.

## Step 3: Code Exchange

Execute a code exchange call to generate a token. The access\_token can be used for subsequent requests to Fleet API on behalf of the user.  
If using the offline\_access scope, save the refresh\_token to generate tokens in the future. The refresh token is single use only and expires after 3 months.  
An invalid\_auth\_code response likely means the code is expired.  
POST https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token

### Parameters

| Name | Required | Example | Description |
| ----- | ----- | ----- | ----- |
| grant\_type | Yes | authorization\_code | Grant type must be authorization\_code. |
| client\_id | Yes | abc-123 | Partner application client ID. |
| client\_secret | Yes | secret-password | Partner application client secret. |
| audience | Yes | [https://fleet-api.prd.na.vn.cloud.tesla.com](https://fleet-api.prd.na.vn.cloud.tesla.com/) | Audience for the generated token. Must be a Fleet API [base URL](https://developer.tesla.com/docs/fleet-api/getting-started/regions-countries#base-urls-by-region). |
| redirect\_uri | Yes | https://example.com/auth/callback | Partner application callback url, spec: [rfc6749](https://www.rfc-editor.org/rfc/rfc6749#section-3.1.2). |
| scope | No | openid offline\_access user\_data vehicle\_device\_data vehicle\_cmds vehicle\_charging\_cmds | Space-delimited list of [scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes). |

### Example Request

\# Authorization code token request  
CODE=\<extract from callback\>  
curl \--request POST \\  
  \--header 'Content-Type: application/x-www-form-urlencoded' \\  
  \--data-urlencode 'grant\_type=authorization\_code' \\  
  \--data-urlencode "client\_id=$CLIENT\_ID" \\  
  \--data-urlencode "client\_secret=$CLIENT\_SECRET" \\  
  \--data-urlencode "code=$CODE" \\  
  \--data-urlencode "audience=$AUDIENCE" \\  
  \--data-urlencode "redirect\_uri=$CALLBACK" \\  
  'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'  
\# Extract access\_token and refresh\_token from this response

## Refresh Tokens

Use the refresh token to generate a new access token and refresh token. When exchanging a refresh token, ensure the new refresh token is saved for use on the next exchange. To support cases where applications fail to save a new refresh token, the most recently used refresh token is valid for up to 24 hours.  
There are two common failure modes for refresh token exchange that return a 401 \- login\_required response:

1. The refresh token is expired or has been cycled out by newer refresh tokens.  
2. The user has reset their password.

### Parameters

| Name | Required | Example | Description |
| ----- | ----- | ----- | ----- |
| grant\_type | Yes | refresh\_token | Grant type must be refresh\_token. |
| client\_id | Yes | abc-123 | Partner application client ID. |
| refresh\_token | Yes | NA\_a90869e9d... | Refresh token from the code exchange response. |

### Example Request

\# Refresh token request  
REFRESH\_TOKEN=\<extract from authorization code token request\>  
curl \--request POST \\  
  \--header 'Content-Type: application/x-www-form-urlencoded' \\  
  \--data-urlencode 'grant\_type=refresh\_token' \\  
  \--data-urlencode "client\_id=$CLIENT\_ID" \\  
  \--data-urlencode "refresh\_token=$REFRESH\_TOKEN" \\  
  'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'

## Scope Changes

Once a user has granted scopes to an application, they can modify scopes or revoke access using the consent management page:  
https://auth.tesla.com/user/revoke/consent?revoke\_client\_id=$CLIENT\_ID\&back\_url=$RETURN\_URL  
Scope modifications are compatible with existing refresh tokens and will be applied to new access tokens.  
Scope additions can be made by sending the user an [/authorize](https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens#step-1-user-authorization) link with prompt\_missing\_scopes=true

# 

# Developer

# [Skip to main content](https://developer.tesla.com/docs/fleet-api/authentication/third-party-business-tokens#main-content)

* [Documentation](https://developer.tesla.com/docs/fleet-api/getting-started/what-is-fleet-api)  
* [Charging](https://developer.tesla.com/docs/charging/roaming)  
* 

# Third-Party Business Tokens

Generate a token on behalf of a business. This allows API calls using the [scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes) granted by the business. Authentication endpoints are not billed. Note: third-party business tokens are incompatible with user endpoints, as there is no user context.

## Step 1: Navigate to Consent Management

Developer administrator navigates to [Tesla for Business](https://www.tesla.com/teslaaccount/business).  
Select "Account" Tab.  
Select "Consent Management" under Access Management in the sidemenu.

## Step 2: Generate Invitation

Click on the "Request Consent" button.  
Select a developer application from the dropdown menu.  
Enter email of a business admin and submit.  
An email will be sent to the business contact to approve the request from 'noreply@tesla.com' with the following subject "Access Request from *application\_name*".

## Step 3: Authorize Application

Business contact opens the approval email and signs in with their admin credentials.  
They will be prompted to select a business account and grant application scopes.

## Step 4: Obtain Authorization Code

After access has been granted, a developer administrator can obtain the authorization code from consent management page within [Tesla for Business](https://www.tesla.com/teslaaccount/business).

## Step 5: Generate Third-Party Business Token

Execute the following request to generate a token.  
POST https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token

### Parameters

| Name | Required | Example | Description |
| ----- | ----- | ----- | ----- |
| grant\_type | Yes | client\_credentials | Grant type must be client\_credentials. |
| client\_id | Yes | abc-123 | Partner application client ID that was granted access |
| client\_secret | Yes | secret-password | Partner application client secret. |
| scope | Yes | user\_data vehicle\_device\_data vehicle\_cmds vehicle\_charging\_cmds | Space delimited list of [scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview#scopes) |
| audience | Yes | [https://fleet-api.prd.na.vn.cloud.tesla.com](https://fleet-api.prd.na.vn.cloud.tesla.com/) | Audience for the generated token. Must be a Fleet API [base URL](https://developer.tesla.com/docs/fleet-api/getting-started/regions-countries#base-urls-by-region). |
| auth\_code | Yes | 7baf90cda... | Authorization code obtained from Step 4 |

### Example Request

\# Third-party business token request  
curl \--request POST \\  
  \--header 'Content-Type: application/x-www-form-urlencoded' \\  
  \--data-urlencode 'grant\_type=client\_credentials' \\  
  \--data-urlencode "client\_id=$CLIENT\_ID" \\  
  \--data-urlencode "client\_secret=$CLIENT\_SECRET" \\  
  \--data-urlencode "auth\_code=$AUTHCODE" \\  
  \--data-urlencode "audience=$AUDIENCE" \\  
  \--data-urlencode "scope=$SCOPE" \\  
  'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'  
\# Extract access\_token from this response

# Vehicle Endpoints

## Endpoints

### drivers

GET /api/1/vehicles/{vehicle\_tag}/drivers  
Returns all allowed drivers for a vehicle. This endpoint is only available for the vehicle owner.

### drivers remove

DELETE /api/1/vehicles/{vehicle\_tag}/drivers  
Removes driver access from a vehicle. Share users can only remove their own access. Owners can remove share access or their own.

### eligible\_subscriptions

GET /api/1/dx/vehicles/subscriptions/eligibility?vin={vin}  
Returns eligible vehicle subscriptions.

### eligible\_upgrades

GET /api/1/dx/vehicles/upgrades/eligibility?vin={vin}  
Returns eligibile vehicle upgrades.

### fleet\_status

POST /api/1/vehicles/fleet\_status  
Checks whether vehicles can accept Tesla commands protocol for the partner's public key. Also returns the version of the Fleet Telemetry client the vehicle is running. When called with one vin, discounted\_device\_data state is also returned. Calling with one vin is recommended.

### fleet\_telemetry\_config create

POST /api/1/vehicles/fleet\_telemetry\_config  
Configures vehicles to connect to a self-hosted [fleet-telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry) server. This endpoint should be called through the Vehicle Command Proxy. The configured private key will be used to sign the configuration. The endpoint can be used to create or update configurations.  
Available fields are described on the [Available Data](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) page.  
Note: legacy applications configured using a CSR may still call this endpoint directly. It is recommended to transition to using the vehicle-command proxy.  
If any specified VINs are not configured, the response will include skipped\_vehicles. VINs may be rejected for a few reasons:

* missing\_key: The virtual key has not been added to the vehicle. [Distributing a public key](https://github.com/teslamotors/vehicle-command?tab=readme-ov-file#distributing-your-public-key).  
* unsupported\_hardware: Pre-2021 Model S and X are not supported.  
* unsupported\_firmware:  
  * If calling directly, vehicles running firmware version earlier than 2023.20.  
  * If using the vehicle-command HTTP proxy, vehicles running firmware version earlier than 2024.26.  
* max\_configs: Vehicles that already have five configurations present.

Fleet Telemetry configuration will automatically be removed if a user revokes an application's access.

### fleet\_telemetry\_config delete

DELETE /api/1/vehicles/{vehicle\_tag}/fleet\_telemetry\_config  
Remove a fleet telemetry configuration from a vehicle. Removes the configuration for any vehicle if called with a partner token.

### fleet\_telemetry\_config get

GET /api/1/vehicles/{vehicle\_tag}/fleet\_telemetry\_config  
Fetches a vehicle's fleet telemetry config. synced set to true means the vehicle has adopted the target config. synced set to false means the vehicle will attempt to adopt the target config when it next establishes a backend connection. Note that if vehicle only allows 3 partners per vehicle for streaming via fleet telemetry. If limit\_reached set to true, vehicle has reached max supported applications and new fleet streaming requests cannot be added to the vehicle

### fleet\_telemetry\_config\_jws

POST /api/1/vehicles/fleet\_telemetry\_config\_jws  
Configures vehicles to connect to a self-hosted [fleet-telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry) server by accepting a signed configuration token.  
It is not recommended to use this endpoint directly.  
The recommended approach for configuring vehicles is calling the [fleet\_telemetry\_config create](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints#fleet-telemetry-config-create) endpoint through the [vehicle-command](https://github.com/teslamotors/vehicle-command) proxy. This will automatically sign the configuration using the configured private key and forward the request to this endpoint.  
If using this endpoint directly, the JWS token must be crafted using a Schnorr signatures algorithm using [NIST P-256](https://csrc.nist.gov/csrc/media/events/workshop-on-elliptic-curve-cryptography-standards/documents/papers/session6-adalier-mehmet.pdf) and SHA-256.  
VINs may be rejected for a few reasons:

* missing\_key: The virtual key has not been added to the vehicle. [Distributing a public key](https://github.com/teslamotors/vehicle-command?tab=readme-ov-file#distributing-your-public-key).  
* unsupported\_hardware: Pre-2021 Model S and X are not supported.  
* unsupported\_firmware: Vehicles running firmware version earlier than 2024.26.

### fleet\_telemetry\_errors

GET /api/1/vehicles/{vehicle\_tag}/fleet\_telemetry\_errors  
Returns recent fleet telemetry errors reported for the specified vehicle after receiving the config.

### list

GET /api/1/vehicles  
Returns vehicles belonging to the account. This endpoint is paginated with a default page size of 100 vehicles.

### mobile\_enabled

GET /api/1/vehicles/{vehicle\_tag}/mobile\_enabled  
Returns whether or not mobile access is enabled for the vehicle.

### nearby\_charging\_sites

GET /api/1/vehicles/{vehicle\_tag}/nearby\_charging\_sites  
Returns the charging sites near the current location of the vehicle.

### options

GET /api/1/dx/vehicles/options?vin={vin}  
Returns vehicle option details.

### recent\_alerts

GET /api/1/vehicles/{vehicle\_tag}/recent\_alerts  
List of recent alerts

### release notes

GET /api/1/vehicles/{vehicle\_tag}/release\_notes  
Returns firmware release notes.

### service\_data

GET /api/1/vehicles/{vehicle\_tag}/service\_data  
Fetches information about the service status of the vehicle.

### share\_invites

GET /api/1/vehicles/{vehicle\_tag}/invitations  
Returns the active share invites for a vehicle. This endpoint is paginated with a max page size of 25 records.

### share\_invites create

POST /api/1/vehicles/{vehicle\_tag}/invitations

* Each invite link is for single-use and expires after 24 hours.  
* An account that uses the invite will gain Tesla app access to the vehicle, which allows it to do the following:  
  * View the live location of the vehicle.  
  * Send remote commands.  
  * Download the user's Tesla profile to the vehicle.  
* To remove access, use the revoke API.  
* If a user does not have the Tesla app installed, they will be directed to this [webpage](https://www.tesla.com/_rs/test) for guidance.  
* A user can set up their phone as key with the Tesla app when in proximity of the vehicle.  
* The app access provides DRIVER privileges, which do not encompass all OWNER features.  
* Up to five drivers can be added at a time .  
* This API does not require the car to be online.

### share\_invites redeem

POST /api/1/invitations/redeem  
Redeems a share invite. Once redeemed, the account will gain access to the vehicle within the Tesla app.

### share\_invites revoke

POST /api/1/vehicles/{vehicle\_tag}/invitations/{id}/revoke  
Revokes a share invite. This invalidates the share and makes the link invalid.

### signed\_command

POST /api/1/vehicles/{vehicle\_tag}/signed\_command  
Signed Commands is a generic endpoint replacing legacy commands. It accepts any of the scopes listed above, depending on the type of command. It uses the Tesla Vehicle Command Protocol to execute commands on a vehicle. Please see the [vehicle command SDK \- tesla-http-proxy](https://github.com/teslamotors/vehicle-command) for more information.

### subscriptions

GET /api/1/subscriptions  
Returns the list of vehicles for which this mobile device currently subscribes to push notifications.

### subscriptions set

POST /api/1/subscriptions  
Allows a mobile device to specify which vehicles to receive push notifications from. When calling from a mobile device, it is sufficient to only provide the vehicle IDs to which the mobile device wishes to subscribe to.

### vehicle

GET /api/1/vehicles/{vehicle\_tag}  
Returns information about a vehicle.

### vehicle\_data

GET /api/1/vehicles/{vehicle\_tag}/vehicle\_data  
Makes a live call to the vehicle to fetch realtime information. Regularly polling this endpoint is not recommended and will be expensive. Instead, [Fleet Telemetry](https://developer.tesla.com/docs/fleet-api/fleet-telemetry) allows the vehicle to push data directly to a server whenever it is online.  
For vehicles running firmware versions 2023.38+, location\_data is required to fetch vehicle location. This will result in a location sharing icon to show on the vehicle UI.

### vehicle\_subscriptions

GET /api/1/vehicle\_subscriptions  
Returns the list of vehicles for which this mobile device currently subscribes to push notifications.

### vehicle\_subscriptions set

POST /api/1/vehicle\_subscriptions  
Allows a mobile device to specify which vehicles to receive push notifications from. It is sufficient to only provide the vehicle IDs to which a mobile device wishes to subscribe to.

### wake\_up

POST /api/1/vehicles/{vehicle\_tag}/wake\_up  
Wakes the vehicle from sleep, which is a state to minimize idle energy consumption.

### warranty\_details

GET /api/1/dx/warranty/details  
Returns the warranty information for a vehicle.  
