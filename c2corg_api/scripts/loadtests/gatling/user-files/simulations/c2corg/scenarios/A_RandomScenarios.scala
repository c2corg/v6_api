package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class A_RandomScenarios extends Simulation {

  val topoguideAnonymous = exec(Homepage.init)
    .pause(8)
    .exec(Homepage.browse)
    .pause(6)
    .exec(Outing.view)
    .pause(14)
    .exec(Route.view)
    .pause(10)
    .exec(Waypoint.view)

  val topoguideAuth = exec(Homepage.init)
    .pause(1)
    .exec(Auth.login)
    .pause(10)
    .exec(Homepage.initAuth)
    .pause(8)
    .exec(Homepage.browseAuth)
    .pause(4)
    .exec(Outing.view)
    .pause(9)
    .exec(Route.view)
    .pause(10)
    .exec(Image.upload)
    .pause(5)
    .exec(Outing.add)

  val topoguideAdvancedSearch = exec(Homepage.init)
    .pause(4)
    .exec(Route.advancedSearchInit)
    .pause(5)
    .exec(Route.advancedSearch)
    .pause(5)
    .exec(Route.view)

  val forumAnonymous = exec(Forum.init)
    .pause(1)
    .exec(Forum.open)
    .pause(6)
    .exec(Forum.scroll)
    .pause(8)
    .exec(Forum.scroll)
    .pause(1)
    .exec(Topic.open)
    .pause(24)
    .exec(Topic.scroll) 

  val forumAuth = exec(Forum.init)
    .pause(2)
    .exec(Auth.loginForum)
    .pause(8)
    .exec(Forum.post)

  val randomUser = scenario("A_RandomScenarios").randomSwitch(
    25.0   -> forumAnonymous,
    5.0    -> forumAuth,
    45.0   -> topoguideAnonymous,
    20.0   -> topoguideAdvancedSearch,
    5.0    -> topoguideAuth
  )

  val httpProtocol = http
        .inferHtmlResources(C2corgConf.black_list, WhiteList())
        .acceptHeader("*/*")
        .acceptEncodingHeader("gzip, deflate")

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(randomUser.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
